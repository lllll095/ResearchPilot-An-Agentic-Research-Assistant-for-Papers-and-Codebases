import json
import re
from typing import Any

from pydantic import ValidationError

from research_pilot.core.action import ActionType, AgentAction
from research_pilot.core.llm_client import OpenAICompatibleLLMClient
from research_pilot.core.state import AgentState


class LLMAgentPolicy:
    """LLM-driven policy for deciding the next AgentAction.

    The LLM must return one JSON object.
    This policy parses, normalizes, and validates the JSON object.
    """

    KNOWN_TOOLS = {
        "list_files",
        "read_file",
        "save_note",
        "shell",
        "todo_write",
        "todo_read",
    }

    def __init__(self, llm_client: OpenAICompatibleLLMClient):
        self.llm_client = llm_client

    def next_action(self, state: AgentState, context: str) -> AgentAction:
        messages = [
            {
                "role": "system",
                "content": self._system_prompt(),
            },
            {
                "role": "user",
                "content": context,
            },
        ]

        raw_output = self.llm_client.complete(messages)

        try:
            payload = self._extract_json(raw_output)
            payload = self._normalize_payload(payload)
            action = AgentAction.model_validate(payload)
            action = self._validate_action(action)
            action = self._apply_completion_guard(state, action)
            return action

        except (json.JSONDecodeError, ValidationError, ValueError, TypeError) as exc:
            return AgentAction(
                action_type=ActionType.FINAL_ANSWER,
                final_answer=(
                    "I could not produce a valid AgentAction JSON. "
                    f"Parsing error: {exc}"
                ),
                thought_summary="The LLM output could not be parsed safely.",
            )

    def _system_prompt(self) -> str:
        return """You are the decision policy of an Agent Harness.

You do not directly execute tools.
You only decide the next structured action.

You must return exactly one JSON object.
Do not use markdown.
Do not wrap the JSON in code fences.
Do not include extra explanations outside JSON.
Do not reveal private chain-of-thought.
Use thought_summary only as a short one-sentence summary.

You can return one of two action types.

1. Tool call:

{
  "action_type": "tool_call",
  "tool_name": "list_files",
  "tool_input": {
    "path": "."
  },
  "thought_summary": "I need to inspect the project structure."
}

2. Final answer:

{
  "action_type": "final_answer",
  "final_answer": "I inspected the project and saved a short note.",
  "thought_summary": "The task is complete."
}

Todo rules:
- For any multi-step task, first create a todo list using todo_write.
- Keep the todo list short and concrete.
- Use todo_write to update statuses when a major step starts or finishes.
- Use status values exactly: pending, in_progress, completed, cancelled.
- Before final_answer, make sure all relevant todo items are completed or cancelled.
- If the current todo list is empty and the task has multiple requirements, call todo_write first.

Tool rules:
- Use only tools listed in the context.
- Prefer list_files and read_file before using shell.
- Use shell only when necessary.
- If the user asks you to save a note, call save_note before final_answer.
- If the user asks you to inspect a project, list files first.
- Do not return final_answer until the user's explicitly requested actions are completed.
- If a previous tool failed, choose another safe action or return final_answer.
"""

    def _extract_json(self, text: str) -> dict[str, Any]:
        """Extract a JSON object from raw LLM output."""

        stripped = text.strip()

        if stripped.startswith("{") and stripped.endswith("}"):
            return json.loads(stripped)

        fence_match = re.search(
            r"```(?:json)?\s*(\{.*?\})\s*```",
            stripped,
            flags=re.DOTALL,
        )
        if fence_match:
            return json.loads(fence_match.group(1))

        object_match = re.search(r"(\{.*\})", stripped, flags=re.DOTALL)
        if object_match:
            return json.loads(object_match.group(1))

        raise json.JSONDecodeError("No JSON object found", stripped, 0)

    def _normalize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Normalize common LLM JSON mistakes into the AgentAction schema."""

        if not isinstance(payload, dict):
            raise TypeError("LLM output JSON must be an object.")

        payload = dict(payload)

        raw_action_type = str(payload.get("action_type", "")).lower().strip()
        tool_name = payload.get("tool_name")

        # Common variants for tool calls.
        if raw_action_type in {"tool_call", "tool", "call_tool", "use_tool"}:
            payload["action_type"] = "tool_call"

        # Sometimes the LLM incorrectly uses the tool name as action_type.
        elif raw_action_type in self.KNOWN_TOOLS:
            payload["action_type"] = "tool_call"
            payload.setdefault("tool_name", raw_action_type)

        # If tool_name exists, we can infer this is a tool call.
        elif tool_name:
            payload["action_type"] = "tool_call"

        # Common variants for final answers.
        elif raw_action_type in {
            "final_answer",
            "final",
            "answer",
            "final_response",
            "respond",
        }:
            payload["action_type"] = "final_answer"

        else:
            raise ValueError(f"Unknown action_type: {raw_action_type}")

        if payload["action_type"] == "tool_call":
            if "tool_input" not in payload:
                if "input" in payload:
                    payload["tool_input"] = payload.pop("input")
                elif "arguments" in payload:
                    payload["tool_input"] = payload.pop("arguments")
                else:
                    # If the model puts tool arguments at top level, collect them.
                    reserved = {
                        "action_type",
                        "tool_name",
                        "tool_input",
                        "final_answer",
                        "thought_summary",
                    }
                    inferred_input = {
                        key: value
                        for key, value in payload.items()
                        if key not in reserved
                    }
                    payload["tool_input"] = inferred_input

            if payload.get("tool_name") is None:
                raise ValueError("tool_call requires tool_name")

        if payload["action_type"] == "final_answer":
            if "final_answer" not in payload and "answer" in payload:
                payload["final_answer"] = payload["answer"]

        return payload

    def _validate_action(self, action: AgentAction) -> AgentAction:
        """Apply minimal safety validation to the parsed action."""

        if action.action_type == ActionType.TOOL_CALL:
            if not action.tool_name:
                raise ValueError("tool_call action requires tool_name")
            if action.final_answer is not None:
                action.final_answer = None

        if action.action_type == ActionType.FINAL_ANSWER:
            if not action.final_answer:
                raise ValueError("final_answer action requires final_answer")
            action.tool_name = None
            action.tool_input = {}

        return action

    def _apply_completion_guard(
        self,
        state: AgentState,
        action: AgentAction,
    ) -> AgentAction:
        """Prevent premature final_answer for simple required actions."""

        if action.action_type != ActionType.FINAL_ANSWER:
            return action

        if self._goal_requires_note(state.user_goal) and not self._has_successful_tool_call(
            state,
            "save_note",
        ):
            note_content = self._build_auto_note_content(state)

            return AgentAction(
                action_type=ActionType.TOOL_CALL,
                tool_name="save_note",
                tool_input={
                    "title": "project_inspection_summary",
                    "content": note_content,
                },
                thought_summary=(
                    "The user asked to save a note, so I must call save_note "
                    "before returning the final answer."
                ),
            )

        return action

    def _goal_requires_note(self, user_goal: str) -> bool:
        """Detect whether the user explicitly asks for a saved note."""

        lowered = user_goal.lower()

        note_keywords = [
            "save a note",
            "save note",
            "saved note",
            "write a note",
            "保存笔记",
            "保存一条笔记",
            "记录笔记",
        ]

        return any(keyword in lowered for keyword in note_keywords)

    def _has_successful_tool_call(self, state: AgentState, tool_name: str) -> bool:
        """Check whether a tool has been successfully called before."""

        for step in state.steps:
            if step.action.tool_name != tool_name:
                continue

            if step.observation is not None and step.observation.success:
                return True

        return False

    def _build_auto_note_content(self, state: AgentState) -> str:
        """Build a simple note from previous observations."""

        lines = [
            "# Project Inspection Summary",
            "",
            f"User goal: {state.user_goal}",
            "",
            "## Observations",
            "",
        ]

        for step in state.steps:
            if step.observation is None:
                continue

            content = step.observation.content
            if len(content) > 1500:
                content = content[:1500] + "\n\n[Observation truncated]"

            lines.append(f"### Step {step.step_id}: {step.action.tool_name}")
            lines.append("")
            lines.append("```text")
            lines.append(content)
            lines.append("```")
            lines.append("")

        return "\n".join(lines)