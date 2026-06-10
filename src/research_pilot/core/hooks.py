from research_pilot.core.action import AgentAction
from research_pilot.core.state import AgentState, AgentStep


class HookManager:
    """Minimal hook manager around the Agent loop.

    Phase 2.5 keeps hooks lightweight.

    Current hook behavior:
    - Inject a todo nag reminder if the Agent has not updated todo for several steps.
    """

    def __init__(self, todo_nag_interval: int = 3):
        self.todo_nag_interval = todo_nag_interval

    def on_run_start(self, state: AgentState) -> None:
        state.todo_reminder = None

    def before_action(self, state: AgentState, action: AgentAction) -> AgentAction:
        return action

    def after_step(self, state: AgentState, step: AgentStep) -> None:
        self._update_todo_reminder(state)

    def on_run_end(self, state: AgentState) -> None:
        pass

    def _update_todo_reminder(self, state: AgentState) -> None:
        """Add a soft reminder if todo has not been updated recently."""

        if state.todo_list.is_empty():
            state.todo_reminder = None
            return

        steps_since_todo = self._steps_since_last_todo_write(state)

        if steps_since_todo >= self.todo_nag_interval and not state.todo_list.all_done():
            state.todo_reminder = (
                f"You have not updated the todo list for {steps_since_todo} steps. "
                "Review the current todo list. If a task has started or completed, "
                "call todo_write to update its status before continuing."
            )
        else:
            state.todo_reminder = None

    def _steps_since_last_todo_write(self, state: AgentState) -> int:
        """Count how many steps have passed since the last todo_write call."""

        count = 0

        for step in reversed(state.steps):
            if step.action.tool_name == "todo_write":
                return count
            count += 1

        return count