import os
import signal
import subprocess
import sys
import threading
import time
from typing import Any

from research_pilot.core.observation import Observation
from research_pilot.core.permission import PermissionChecker
from research_pilot.core.tool import BaseTool, ToolSpec

# ---------------------------------------------------------------------------
# Background process registry
# ---------------------------------------------------------------------------

_background_processes: dict[str, dict[str, Any]] = {}
_process_lock = threading.Lock()
_process_counter = 0


def _next_bg_id() -> str:
    global _process_counter
    with _process_lock:
        _process_counter += 1
        return f"bg_{_process_counter}"


def _kill_process_tree(pid: int) -> None:
    """Kill a process and all its children."""
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True, timeout=5,
            )
        else:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
    except (ProcessLookupError, OSError):
        pass


def _cleanup_finished_processes() -> None:
    """Remove finished processes from the registry."""
    with _process_lock:
        finished = [
            pid for pid, info in _background_processes.items()
            if info["process"].poll() is not None
        ]
        for pid in finished:
            del _background_processes[pid]


# ---------------------------------------------------------------------------
# ShellTool
# ---------------------------------------------------------------------------

class ShellTool(BaseTool):
    """Run shell commands with improved process management.

    Supports:
    - Synchronous execution with configurable timeout
    - Background execution (async) with process tracking
    - Working directory control
    - Process tree termination on timeout
    """

    name = "shell"
    description = "Run a shell command with cwd, timeout, and background options."

    def __init__(self, permission_checker: PermissionChecker, timeout: int = 30):
        self.permission_checker = permission_checker
        self.timeout = timeout

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "command": "Shell command to run (required).",
                "cwd": "Working directory (optional).",
                "timeout": "Timeout in seconds (optional, default 30).",
                "background": 'Set to "true" to run in background (returns process ID).',
            },
            output_schema={
                "stdout": "Command output.",
                "returncode": "Exit code.",
                "bg_id": "Background process ID (only in background mode).",
            },
        )

    def run(self, tool_input: dict, state=None) -> Observation:
        command = tool_input.get("command", "").strip()
        cwd = tool_input.get("cwd") or None
        timeout = int(tool_input.get("timeout", self.timeout))
        background = tool_input.get("background", "").lower() == "true"

        if not command:
            return Observation(
                success=False,
                content="Missing input: command",
                error="MissingCommand",
            )

        permission = self.permission_checker.check_shell_command(command)
        if not permission.allowed:
            return Observation(
                success=False,
                content=permission.reason,
                error="PermissionDenied",
            )

        if background:
            return self._run_background(command, cwd)
        return self._run_foreground(command, cwd, timeout)

    def _run_foreground(self, command: str, cwd: str | None, timeout: int) -> Observation:
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
            )
        except subprocess.TimeoutExpired:
            return Observation(
                success=False,
                content=f"Command timed out after {timeout}s.",
                error="Timeout",
                metadata={"command": command},
            )

        output = result.stdout.strip() or result.stderr.strip() or "(no output)"

        return Observation(
            success=result.returncode == 0,
            content=output[:4000],
            data={
                "stdout": output[:4000],
                "returncode": result.returncode,
            },
            metadata={"returncode": result.returncode, "command": command},
            error=None if result.returncode == 0 else "NonZeroExit",
        )

    def _run_background(self, command: str, cwd: str | None) -> Observation:
        try:
            proc = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=cwd,
            )
        except Exception as exc:
            return Observation(
                success=False,
                content=f"Failed to start background process: {exc}",
                error="ProcessStartError",
            )

        bg_id = _next_bg_id()
        with _process_lock:
            _background_processes[bg_id] = {
                "pid": proc.pid,
                "process": proc,
                "command": command,
                "started_at": time.time(),
            }

        return Observation(
            success=True,
            content=f"Background process started.\nID: {bg_id}\nPID: {proc.pid}",
            data={
                "bg_id": bg_id,
                "pid": proc.pid,
            },
            metadata={
                "bg_id": bg_id,
                "pid": proc.pid,
                "command": command,
            },
        )


# ---------------------------------------------------------------------------
# ShellBgTool
# ---------------------------------------------------------------------------

class ShellBgTool(BaseTool):
    """Manage background shell processes."""

    name = "shell_bg"
    description = "List, check status, or kill background processes started by ShellTool."

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "action": "One of: list, status, kill, output.",
                "bg_id": "Background process ID (required for status/kill/output).",
            },
        )

    def run(self, tool_input: dict, state=None) -> Observation:
        action = tool_input.get("action", "list")
        bg_id = tool_input.get("bg_id", "")

        _cleanup_finished_processes()

        if action == "list":
            return self._list_processes()

        if not bg_id:
            return Observation(
                success=False,
                content="bg_id is required for this action.",
                error="MissingBgId",
            )

        if action == "status":
            return self._status_process(bg_id)
        elif action == "kill":
            return self._kill_process(bg_id)
        elif action == "output":
            return self._output_process(bg_id)
        else:
            return Observation(
                success=False, content=f"Unknown action: {action}",
                error="UnknownAction",
            )

    def _list_processes(self) -> Observation:
        if not _background_processes:
            return Observation(success=True, content="No background processes running.")

        lines = ["Background processes:"]
        with _process_lock:
            for bg_id, info in _background_processes.items():
                proc = info["process"]
                status = "running" if proc.poll() is None else f"exited ({proc.returncode})"
                runtime = int(time.time() - info["started_at"])
                lines.append(f"  {bg_id} (PID {info['pid']}): {status}, {runtime}s")
        return Observation(
            success=True,
            content="\n".join(lines),
            data={"bg_ids": list(_background_processes.keys())},
        )

    def _status_process(self, bg_id: str) -> Observation:
        with _process_lock:
            info = _background_processes.get(bg_id)
        if not info:
            return Observation(success=False, content=f"No such process: {bg_id}", error="ProcessNotFound")

        proc = info["process"]
        status = "running" if proc.poll() is None else f"exited ({proc.returncode})"
        return Observation(
            success=True,
            content=f"PID {info['pid']}: {status}",
            data={"bg_id": bg_id, "pid": info["pid"], "status": status},
        )

    def _kill_process(self, bg_id: str) -> Observation:
        with _process_lock:
            info = _background_processes.get(bg_id)
        if not info:
            return Observation(success=False, content=f"No such process: {bg_id}", error="ProcessNotFound")

        proc = info["process"]
        if proc.poll() is not None:
            with _process_lock:
                del _background_processes[bg_id]
            return Observation(success=True, content=f"Process {bg_id} already exited.")

        _kill_process_tree(proc.pid)
        with _process_lock:
            del _background_processes[bg_id]
        return Observation(success=True, content=f"Process {bg_id} (PID {info['pid']}) killed.")

    def _output_process(self, bg_id: str) -> Observation:
        with _process_lock:
            info = _background_processes.get(bg_id)
        if not info:
            return Observation(success=False, content=f"No such process: {bg_id}", error="ProcessNotFound")

        proc = info["process"]
        stdout = ""
        stderr = ""
        try:
            stdout, stderr = proc.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            return Observation(
                success=True,
                content=f"Process {bg_id} still running. No output yet.",
            )

        output = stdout.strip() or stderr.strip() or "(no output)"
        with _process_lock:
            del _background_processes[bg_id]
        return Observation(
            success=proc.returncode == 0,
            content=output[:4000],
            data={"stdout": stdout[:2000], "stderr": stderr[:2000]},
        )
