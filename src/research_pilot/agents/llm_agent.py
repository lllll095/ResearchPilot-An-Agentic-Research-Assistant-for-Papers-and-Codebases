import json
import re
from typing import Any

from pydantic import ValidationError

from research_pilot.core.action import ActionType, AgentAction
from research_pilot.core.llm_client import OpenAICompatibleLLMClient
from research_pilot.core.state import AgentState
from research_pilot.prompts.agent_prompt import AgentSystemPromptBuilder


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
        "web_search",
        "save_report",
        "summarize_evidence",
        "paper_search",
        "paper_download",
        "engineered_rag_index",
        "engineered_rag_search",
        "engineered_rag_answer",
        "write_evidence_answer",
        "code_map",
        "code_search",
        "code_read",
    }

    def __init__(self, llm_client, tool_specs):
        self.llm_client = llm_client
        self.tool_specs = tool_specs

        self.KNOWN_TOOLS = self._extract_known_tools(tool_specs)

        # print(f"[LLMAgentPolicy] Known tools: {sorted(self.KNOWN_TOOLS)}")

    def _build_system_prompt(self) -> str:
        """Build system prompt from modular prompt sections."""

        builder = AgentSystemPromptBuilder(
            tool_specs=self.tool_specs,
            include_todo_rules=True,
            include_research_rules=True,
            include_paper_rules=True,
            include_engineered_rag_rules=True,
            include_evidence_answer_rules=True,
            include_codebase_rules=True,
            include_code_answer_rules=True,
        )

        return builder.build()

    def _extract_known_tools(self, tool_specs) -> set[str]:
        """Extract available tool names from tool specs.

        This makes the LLM action normalizer automatically recognize newly
        registered tools, such as code_map, code_search, and code_read.
        """

        known_tools: set[str] = set()

        if tool_specs is None:
            return known_tools

        # Case 1: tool_specs is a dict: {"tool_name": spec}
        if isinstance(tool_specs, dict):
            for name in tool_specs.keys():
                known_tools.add(str(name).lower().strip())

            for spec in tool_specs.values():
                name = getattr(spec, "name", None)
                if name:
                    known_tools.add(str(name).lower().strip())

            return known_tools

        # Case 2: tool_specs is a list of ToolSpec objects or dicts
        for spec in tool_specs:
            if isinstance(spec, dict):
                name = spec.get("name")
            else:
                name = getattr(spec, "name", None)

            if name:
                known_tools.add(str(name).lower().strip())

        return known_tools

    def next_action(self, state: AgentState, context: str) -> AgentAction:
        passthrough_action = self._passthrough_last_evidence_answer(state)
        if passthrough_action is not None:
            return passthrough_action

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
        """Backward-compatible wrapper for the old prompt API."""

        return self._build_system_prompt()

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

        known_tools = {str(name).lower().strip() for name in self.KNOWN_TOOLS}

        # Common variants for tool calls.
        if raw_action_type in {"tool_call", "tool", "call_tool", "use_tool"}:
            payload["action_type"] = "tool_call"

        # Sometimes the LLM incorrectly uses the tool name as action_type.
        # Example:
        # {"action_type": "code_read", "tool_input": {"path": "..."}}
        # becomes:
        # {"action_type": "tool_call", "tool_name": "code_read", "tool_input": {"path": "..."}}
        elif raw_action_type in known_tools:
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
                elif "args" in payload:
                    payload["tool_input"] = payload.pop("args")
                else:
                    # If the model puts tool arguments at top level, collect them.
                    reserved = {
                        "action_type",
                        "tool_name",
                        "tool_input",
                        "final_answer",
                        "answer",
                        "thought_summary",
                    }
                    inferred_input = {
                        key: value
                        for key, value in payload.items()
                        if key not in reserved
                    }
                    payload["tool_input"] = inferred_input

            if payload.get("tool_input") is None:
                payload["tool_input"] = {}

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
    
    def _passthrough_last_evidence_answer(self, state) -> AgentAction | None:
        """If write_evidence_answer just succeeded, return it directly.

        This avoids compressing a citation-aware answer into a weaker final answer.
        """

        if not state.steps:
            return None

        last_step = state.steps[-1]

        if last_step.action.tool_name != "write_evidence_answer":
            return None

        if last_step.observation is None or not last_step.observation.success:
            return None

        answer = last_step.observation.content

        if not answer:
            return None

        return AgentAction(
            action_type=ActionType.FINAL_ANSWER,
            final_answer=answer,
            thought_summary=(
                "The citation-aware answer has already been generated, "
                "so I should return it directly."
            ),
        )