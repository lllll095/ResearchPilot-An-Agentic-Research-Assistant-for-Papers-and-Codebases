from datetime import datetime
from typing import Protocol

from rich.console import Console

from research_pilot.core.action import ActionType, AgentAction
from research_pilot.core.context_manager import ContextManager
from research_pilot.core.hooks import HookManager
from research_pilot.core.state import AgentState, AgentStep
from research_pilot.core.tool_runtime import ToolRuntime
from research_pilot.core.trace import TraceStore


class AgentPolicy(Protocol):
    """Interface for an Agent decision policy."""

    def next_action(self, state: AgentState, context: str) -> AgentAction:
        ...


class AgentLoop:
    """The core Agent loop.

    This is the central runtime of ResearchPilot.
    """

    def __init__(
        self,
        policy: AgentPolicy,
        tool_runtime: ToolRuntime,
        context_manager: ContextManager,
        trace_store: TraceStore,
        hook_manager: HookManager | None = None,
        max_steps: int = 10,
    ):
        self.policy = policy
        self.tool_runtime = tool_runtime
        self.context_manager = context_manager
        self.trace_store = trace_store
        self.hook_manager = hook_manager or HookManager()
        self.max_steps = max_steps
        self.console = Console()

    def run(self, user_goal: str) -> AgentState:
        state = AgentState(user_goal=user_goal)
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        self.console.rule("[bold blue]Agent Loop Started")
        self.hook_manager.on_run_start(state)

        for step_id in range(1, self.max_steps + 1):
            context = self.context_manager.build_context(state, self.tool_runtime)
            action = self.policy.next_action(state, context)
            action = self.hook_manager.before_action(state, action)

            step = AgentStep(step_id=step_id, action=action)

            if action.action_type == ActionType.FINAL_ANSWER:
                state.final_answer = action.final_answer or ""
                state.add_step(step)
                self.trace_store.save_step(run_id, step)
                self.hook_manager.after_step(state, step)
                self.console.print(f"[green]Step {step_id}: final_answer[/green]")
                break

            if action.action_type == ActionType.TOOL_CALL:
                self.console.print(
                    f"[yellow]Step {step_id}: tool_call -> {action.tool_name}[/yellow]"
                )

                observation = self.tool_runtime.execute(action, state=state)
                step.observation = observation
                state.add_step(step)

                self.trace_store.save_step(run_id, step)
                self.hook_manager.after_step(state, step)

                if observation.success:
                    self.console.print(f"[green]Observation:[/green] {observation.content}")
                else:
                    self.console.print(f"[red]Tool error:[/red] {observation.error}")

        else:
            state.final_answer = "Agent stopped because max_steps was reached."

        self.hook_manager.on_run_end(state)
        final_path = self.trace_store.save_final_state(run_id, state)
        self.console.print(f"[dim]Trace saved to: {final_path}[/dim]")

        return state