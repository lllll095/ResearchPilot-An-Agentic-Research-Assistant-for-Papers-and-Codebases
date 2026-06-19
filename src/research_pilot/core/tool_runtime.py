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

        spec = tool.spec()

        # Validate input against schema
        if spec.input_schema:
            error = spec.validate_input(action.tool_input)
            if error is not None:
                return Observation(
                    success=False,
                    content=f"Input validation failed for '{action.tool_name}': {error}",
                    error="InputValidationError",
                    metadata={"tool": action.tool_name, "validation_error": error},
                )

        result = tool.run(action.tool_input, state=state)

        # Validate output data against schema
        if result.success and result.data is not None and spec.output_schema:
            error = spec.validate_output_data(result.data)
            if error is not None:
                return Observation(
                    success=False,
                    content=f"Output validation failed for '{action.tool_name}': {error}",
                    error="OutputValidationError",
                    metadata={"tool": action.tool_name, "validation_error": error},
                )

        return result