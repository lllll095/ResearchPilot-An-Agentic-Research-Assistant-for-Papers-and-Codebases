# src/research_pilot/tools/git_tools.py

"""Git integration tools for ResearchPilot.

Provides tools for checking git status, viewing diffs,
and making commits. These enable the agent to understand
and interact with the codebase version history.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path

from research_pilot.core.observation import Observation
from research_pilot.core.tool import BaseTool, ToolSpec


@dataclass
class GitStatus:
    branch: str
    modified: list[str]
    untracked: list[str]
    staged: list[str]
    ahead: int
    behind: int


def _run_git(args: list[str], cwd: str | None = None) -> tuple[int, str, str]:
    """Run a git command and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=15,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        return -1, "", "Git not found. Is git installed?"
    except subprocess.TimeoutExpired:
        return -1, "", "Git command timed out."
    except Exception as exc:
        return -1, "", f"Git error: {exc}"


class GitStatusTool(BaseTool):
    """Show current git status: branch, modified files, untracked files."""

    name = "git_status"
    description = "Show current git branch and file status (modified, untracked, staged)."

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={"cwd": "Optional working directory. Defaults to current dir."},
            output_schema={
                "branch": "Current git branch name",
                "modified": "List of modified file paths",
                "untracked": "List of untracked file paths",
                "staged": "List of staged file paths",
            },
        )

    def run(self, tool_input: dict, state=None) -> Observation:
        cwd = tool_input.get("cwd")

        # Get branch name
        rc, branch, err = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd)
        if rc != 0:
            return Observation(
                success=False,
                content=f"Not a git repository: {err}" if "not a git repository" in err.lower() else f"Git error: {err}",
                error="GitError",
            )

        # Get status (porcelain format for parsing)
        rc, status_out, err = _run_git(["status", "--porcelain"], cwd=cwd)
        if rc != 0:
            return Observation(
                success=False,
                content=f"Git status failed: {err}",
                error="GitError",
            )

        modified = []
        untracked = []
        staged = []

        for line in status_out.split("\n"):
            if not line.strip():
                continue
            # Porcelain format: XY filename
            xy = line[:2].strip()
            path = line[3:].strip()

            if xy == "M" or xy == " M":
                modified.append(path)
            elif xy == "??":
                untracked.append(path)
            elif xy in ("A", " M", "MM"):
                staged.append(path)

        # Get ahead/behind
        rc, branch_info, _ = _run_git(
            ["rev-list", "--left-right", "--count", "HEAD...@{u}"],
            cwd=cwd,
        )
        ahead = 0
        behind = 0
        if rc == 0 and branch_info:
            parts = branch_info.split("\t")
            if len(parts) == 2:
                ahead = int(parts[0]) if parts[0].isdigit() else 0
                behind = int(parts[1]) if parts[1].isdigit() else 0

        status = GitStatus(
            branch=branch,
            modified=modified,
            untracked=untracked,
            staged=staged,
            ahead=ahead,
            behind=behind,
        )

        # Build human-readable content
        content_lines = [f"Branch: {branch}"]
        if modified:
            content_lines.append(f"Modified ({len(modified)}):")
            for f in modified[:20]:
                content_lines.append(f"  M {f}")
        if untracked:
            content_lines.append(f"Untracked ({len(untracked)}):")
            for f in untracked[:20]:
                content_lines.append(f"  ?? {f}")
        if staged:
            content_lines.append(f"Staged ({len(staged)}):")
            for f in staged[:20]:
                content_lines.append(f"  A {f}")
        if ahead > 0 or behind > 0:
            content_lines.append(f"Remote: {ahead} ahead, {behind} behind")
        if not modified and not untracked and not staged:
            content_lines.append("Working tree clean.")

        return Observation(
            success=True,
            content="\n".join(content_lines),
            data={
                "branch": branch,
                "modified": modified,
                "untracked": untracked,
                "staged": staged,
                "ahead": ahead,
                "behind": behind,
            },
        )


class GitDiffTool(BaseTool):
    """Show git diff for modified files."""

    name = "git_diff"
    description = "Show unstaged changes (git diff). Use --staged to show staged changes."

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "path": "Optional file path to filter diff to specific file.",
                "staged": "Set to 'true' to show staged changes (git diff --staged).",
            },
            output_schema={
                "diff": "Diff output text",
                "files_changed": "Number of files changed",
            },
        )

    def run(self, tool_input: dict, state=None) -> Observation:
        path = tool_input.get("path", "")
        staged = tool_input.get("staged", "").lower() == "true"

        args = ["diff"]
        if staged:
            args.append("--staged")
        if path:
            args.append("--")
            args.append(path)

        rc, diff_out, err = _run_git(args)
        if rc != 0:
            return Observation(
                success=False,
                content=f"Git diff failed: {err}",
                error="GitError",
            )

        if not diff_out:
            return Observation(
                success=True,
                content="No changes to show." if not staged else "No staged changes.",
                data={"diff": "", "files_changed": 0},
            )

        files_changed = len([l for l in diff_out.split("\n") if l.startswith("diff --git")])

        return Observation(
            success=True,
            content=f"Diff ({files_changed} file(s)):\n\n" + diff_out[:5000],
            data={"diff": diff_out, "files_changed": files_changed},
        )


class GitCommitTool(BaseTool):
    """Stage and commit changes."""

    name = "git_commit"
    description = "Create a git commit. Stages all changes by default, or specific files."

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "message": "Commit message (required).",
                "files": "Optional list of file paths to stage. Default: stage all.",
                "allow_empty": "Set to 'true' to allow empty commit.",
            },
        )

    def run(self, tool_input: dict, state=None) -> Observation:
        message = tool_input.get("message", "").strip()
        files = tool_input.get("files", "")
        allow_empty = tool_input.get("allow_empty", "").lower() == "true"

        if not message:
            return Observation(
                success=False,
                content="Commit message is required.",
                error="MissingCommitMessage",
            )

        # Stage files
        if files:
            for f in files.split(","):
                f = f.strip()
                if f:
                    rc, _, err = _run_git(["add", f])
                    if rc != 0:
                        return Observation(
                            success=False,
                            content=f"Failed to stage '{f}': {err}",
                            error="GitStageError",
                        )
        else:
            rc, _, err = _run_git(["add", "-A"])
            if rc != 0:
                return Observation(
                    success=False,
                    content=f"Failed to stage all: {err}",
                    error="GitStageError",
                )

        # Commit
        commit_args = ["commit", "-m", message]
        if allow_empty:
            commit_args.append("--allow-empty")

        rc, out, err = _run_git(commit_args)
        if rc != 0:
            return Observation(
                success=False,
                content=f"Commit failed: {err}",
                error="GitCommitError",
            )

        return Observation(
            success=True,
            content=f"Commit created:\n{out}",
            data={"message": message, "output": out},
        )
