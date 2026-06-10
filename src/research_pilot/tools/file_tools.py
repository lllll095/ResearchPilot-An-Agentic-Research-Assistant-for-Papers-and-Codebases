from pathlib import Path

from research_pilot.core.observation import Observation
from research_pilot.core.permission import PermissionChecker
from research_pilot.core.tool import BaseTool, ToolSpec


class ListFilesTool(BaseTool):
    name = "list_files"
    description = "List files and folders under a directory."

    def __init__(self, permission_checker: PermissionChecker):
        self.permission_checker = permission_checker

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "path": "Directory path to list. Use '.' for the current project root."
            },
        )

    def run(self, tool_input: dict) -> Observation:
        path = tool_input.get("path", ".")
        permission = self.permission_checker.check_file_path(path)

        if not permission.allowed:
            return Observation(
                success=False,
                content=permission.reason,
                error="PermissionDenied",
            )

        target = Path(path)

        if not target.exists():
            return Observation(
                success=False,
                content=f"Path does not exist: {path}",
                error="PathNotFound",
            )

        if not target.is_dir():
            return Observation(
                success=False,
                content=f"Path is not a directory: {path}",
                error="NotADirectory",
            )

        items = []
        for item in sorted(target.iterdir()):
            suffix = "/" if item.is_dir() else ""
            items.append(f"{item.name}{suffix}")

        content = "\n".join(items) if items else "(empty directory)"

        return Observation(
            success=True,
            content=content,
            metadata={"path": str(target)},
        )


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Read a UTF-8 text file."

    def __init__(self, permission_checker: PermissionChecker, max_chars: int = 4000):
        self.permission_checker = permission_checker
        self.max_chars = max_chars

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "path": "Path of the UTF-8 text file to read, such as README.md."
            },
        )

    def run(self, tool_input: dict) -> Observation:
        path = tool_input.get("path")

        if not path:
            return Observation(
                success=False,
                content="Missing input: path",
                error="MissingPath",
            )

        permission = self.permission_checker.check_file_path(path)

        if not permission.allowed:
            return Observation(
                success=False,
                content=permission.reason,
                error="PermissionDenied",
            )

        target = Path(path)

        if not target.exists():
            return Observation(
                success=False,
                content=f"File does not exist: {path}",
                error="FileNotFound",
            )

        if not target.is_file():
            return Observation(
                success=False,
                content=f"Path is not a file: {path}",
                error="NotAFile",
            )

        try:
            text = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return Observation(
                success=False,
                content=f"Cannot decode file as UTF-8: {path}",
                error="DecodeError",
            )

        truncated = text[: self.max_chars]

        if len(text) > self.max_chars:
            truncated += "\n\n[File truncated]"

        return Observation(
            success=True,
            content=truncated,
            metadata={
                "path": str(target),
                "truncated": len(text) > self.max_chars,
            },
        )