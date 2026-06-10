from typing import Any

from research_pilot.core.action import AgentAction
from research_pilot.core.observation import Observation
from research_pilot.core.permission import PermissionChecker
from research_pilot.core.tool import BaseTool, ToolSpec


class ToolRuntime:
    """Registry and executor for tools."""

    def __init__(self, permission_checker: PermissionChecker):
        self.permission_checker = permission_checker
        self.tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        if tool.name in self.tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self.tools[tool.name] = tool

    def list_tools(self) -> list[str]:
        return list(self.tools.keys())

    def tool_specs(self) -> list[ToolSpec]:
        return [tool.spec() for tool in self.tools.values()]

    def execute(self, action: AgentAction, state: Any | None = None) -> Observation:
        if action.tool_name is None:
            return Observation(
                success=False,
                content="No tool name provided.",
                error="MissingToolName",
            )

        tool = self.tools.get(action.tool_name)

        if tool is None:
            return Observation(
                success=False,
                content=f"Tool not found: {action.tool_name}",
                error="ToolNotFound",
                metadata={"available_tools": self.list_tools()},
            )

        return tool.run(action.tool_input, state=state)