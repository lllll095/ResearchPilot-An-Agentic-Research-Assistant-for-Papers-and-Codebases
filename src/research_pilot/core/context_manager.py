import json
from typing import Any

from research_pilot.core.state import AgentState
from research_pilot.core.tool_runtime import ToolRuntime


class ContextManager:
    """Build compact context for the Agent.

    Phase 2 context includes:
    - user goal
    - available tool specs
    - recent steps
    - JSON action requirements

    To avoid prompt pollution, long observations are truncated.
    """

    def __init__(self, max_observation_chars: int = 1200):
        self.max_observation_chars = max_observation_chars

    def build_context(self, state: AgentState, tool_runtime: ToolRuntime) -> str:
        recent_steps = state.steps[-5:]
        tool_specs = [spec.model_dump() for spec in tool_runtime.tool_specs()]

        step_text = "\n".join(
            f"Step {step.step_id}:\n"
            f"  action: {step.action.model_dump()}\n"
            f"  observation: {self._dump_observation(step.observation)}"
            for step in recent_steps
        )

        return f"""User goal:
{state.user_goal}

Available tools:
{json.dumps(tool_specs, indent=2, ensure_ascii=False)}

Recent steps:
{step_text if step_text else "No previous steps."}

You must choose the next action.

Return exactly one JSON object matching one of these schemas.

Tool call schema:
{{
  "action_type": "tool_call",
  "tool_name": "tool_name_here",
  "tool_input": {{}},
  "thought_summary": "short summary"
}}

Final answer schema:
{{
  "action_type": "final_answer",
  "final_answer": "your final answer here",
  "thought_summary": "short summary"
}}
"""

    def _dump_observation(self, observation) -> dict[str, Any] | None:
        if observation is None:
            return None

        payload = observation.model_dump()
        content = payload.get("content", "")

        if isinstance(content, str) and len(content) > self.max_observation_chars:
            payload["content"] = content[: self.max_observation_chars] + (
                "\n\n[Observation truncated for context]"
            )

        return payload