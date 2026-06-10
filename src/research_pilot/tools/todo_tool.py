from research_pilot.core.observation import Observation
from research_pilot.core.todo import TodoList
from research_pilot.core.tool import BaseTool, ToolSpec


class TodoWriteTool(BaseTool):
    name = "todo_write"
    description = "Create or update the current todo list for a multi-step task."

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "items": [
                    {
                        "id": "short unique id, such as '1'",
                        "content": "todo item content",
                        "status": "pending | in_progress | completed | cancelled",
                        "notes": "optional short note",
                    }
                ]
            },
        )

    def run(self, tool_input: dict, state=None) -> Observation:
        if state is None:
            return Observation(
                success=False,
                content="TodoWriteTool requires AgentState.",
                error="MissingState",
            )

        try:
            todo_list = TodoList.model_validate(tool_input)
        except Exception as exc:
            return Observation(
                success=False,
                content=f"Invalid todo list payload: {exc}",
                error="InvalidTodoPayload",
            )

        state.todo_list = todo_list

        return Observation(
            success=True,
            content="Todo list updated:\n" + state.todo_list.render(),
            metadata={
                "num_items": len(state.todo_list.items),
            },
        )


class TodoReadTool(BaseTool):
    name = "todo_read"
    description = "Read the current todo list."

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={},
        )

    def run(self, tool_input: dict, state=None) -> Observation:
        if state is None:
            return Observation(
                success=False,
                content="TodoReadTool requires AgentState.",
                error="MissingState",
            )

        return Observation(
            success=True,
            content=state.todo_list.render(),
            metadata={
                "num_items": len(state.todo_list.items),
            },
        )