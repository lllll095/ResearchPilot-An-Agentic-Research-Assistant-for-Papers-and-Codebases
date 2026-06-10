import subprocess

from research_pilot.core.observation import Observation
from research_pilot.core.permission import PermissionChecker
from research_pilot.core.tool import BaseTool, ToolSpec


class ShellTool(BaseTool):
    name = "shell"
    description = "Run a safe shell command."

    def __init__(self, permission_checker: PermissionChecker, timeout: int = 10):
        self.permission_checker = permission_checker
        self.timeout = timeout

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=(
                "Run a safe shell command. Prefer file tools when possible. "
                "Do not use this for destructive commands."
            ),
            input_schema={
                "command": "Shell command to run, such as 'python --version' or 'pytest'."
            },
        )

    def run(self, tool_input: dict, state=None) -> Observation:
        command = tool_input.get("command")

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

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            return Observation(
                success=False,
                content=f"Command timed out after {self.timeout} seconds.",
                error="Timeout",
            )

        output = result.stdout.strip() or result.stderr.strip() or "(no output)"

        return Observation(
            success=result.returncode == 0,
            content=output[:4000],
            metadata={
                "returncode": result.returncode,
                "command": command,
            },
            error=None if result.returncode == 0 else "NonZeroExit",
        )