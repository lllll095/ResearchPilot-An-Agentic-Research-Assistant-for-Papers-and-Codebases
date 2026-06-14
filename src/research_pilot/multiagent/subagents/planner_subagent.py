# src/research_pilot/multiagent/subagents/planner_subagent.py

import json
from typing import Any

from pydantic import BaseModel, Field

from research_pilot.core.llm_client import OpenAICompatibleLLMClient
from research_pilot.multiagent.base_subagent import (
    BaseSubAgent,
    SubAgentInput,
    SubAgentOutput,
)


class PlannerDecision(BaseModel):
    """Structured decision produced by PlannerSubAgent."""

    task_type: str = Field(
        description=(
            "Task type selected by the planner. "
            "Supported values for now: code_answer, general."
        )
    )
    next_agent: str = Field(
        description=(
            "Next subagent to run. Supported values for now: code, none."
        )
    )
    reason: str = Field(
        description="Short reason for the planning decision."
    )
    rewritten_request: str = Field(
        default="",
        description=(
            "Optional rewritten user request. Useful when conversation context "
            "contains references such as 'it', 'that', or '刚才那个'."
        ),
    )


class PlannerSubAgent(BaseSubAgent):
    """LLM-based planner that decides which subagent should handle the task."""

    name = "planner"
    description = "Use an LLM to decide which subagent should handle the user request."

    def __init__(self, llm_client: OpenAICompatibleLLMClient):
        self.llm_client = llm_client

    def run(self, agent_input: SubAgentInput) -> SubAgentOutput:
        blackboard = agent_input.blackboard

        try:
            decision = self._plan(agent_input)

            blackboard.add_note(
                author=self.name,
                content=(
                    f"Planner selected task_type={decision.task_type}, "
                    f"next_agent={decision.next_agent}. Reason: {decision.reason}"
                ),
                metadata=decision.model_dump(),
            )

            return SubAgentOutput(
                agent_name=self.name,
                success=True,
                content=decision.model_dump_json(indent=2),
                updates={
                    "planner_decision": decision.model_dump(),
                },
            )

        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"

            fallback_decision = self._fallback_decision(
                user_request=blackboard.user_request,
                error=error,
            )

            blackboard.add_note(
                author=self.name,
                content=(
                    "Planner LLM failed. Used fallback decision. "
                    f"Fallback task_type={fallback_decision.task_type}, "
                    f"next_agent={fallback_decision.next_agent}."
                ),
                metadata={
                    "error": error,
                    "fallback_decision": fallback_decision.model_dump(),
                },
            )

            return SubAgentOutput(
                agent_name=self.name,
                success=True,
                content=fallback_decision.model_dump_json(indent=2),
                updates={
                    "planner_decision": fallback_decision.model_dump(),
                    "planner_fallback_error": error,
                },
            )

    def _plan(self, agent_input: SubAgentInput) -> PlannerDecision:
        blackboard = agent_input.blackboard
        context = blackboard.compact_context()

        messages = [
            {
                "role": "system",
                "content": self._system_prompt(),
            },
            {
                "role": "user",
                "content": f"""User request:
{blackboard.user_request}

Optional instruction:
{agent_input.instruction or "(none)"}

Shared blackboard context:
{context}
""",
            },
        ]

        raw = self.llm_client.complete(messages).strip()
        payload = self._parse_json(raw)

        decision = PlannerDecision.model_validate(payload)

        decision = self._normalize_decision(decision)

        return decision

    def _system_prompt(self) -> str:
        return """You are the PlannerSubAgent in a multi-agent research assistant.

Your job is not to answer the user directly.
Your job is to choose which subagent should handle the task.

Currently available subagents:

1. code
- Use this for questions about source code, implementation details, functions,
  classes, modules, project structure, CLI commands, workflow implementation,
  tool implementation, AgentLoop, ToolRuntime, EvidenceStore, TraceStore,
  CodeWorkflowRunner, PaperWorkflowRunner, or other codebase details.

2. none
- Use this only when no available specialized subagent can handle the request.

You must return exactly one JSON object.
Do not use markdown.
Do not wrap the JSON in code fences.
Do not include explanations outside JSON.

JSON schema:

{
  "task_type": "code_answer | general",
  "next_agent": "code | none",
  "reason": "short reason",
  "rewritten_request": "optional rewritten request"
}

Rules:
- For codebase implementation questions, choose task_type="code_answer" and next_agent="code".
- If the user asks in Chinese about 代码, 源码, 实现, 函数, 类, 模块, 调用链, 工作流, or 在哪里, choose the code agent.
- If the user uses references like "it", "that", "刚才那个", use the blackboard context to rewrite the request if possible.
- Do not choose paper/research agents yet because they are not available in this minimal version.
"""

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any]:
        text = raw.strip()

        if text.startswith("```"):
            text = text.strip("`").strip()
            if text.lower().startswith("json"):
                text = text[4:].strip()

        start = text.find("{")
        end = text.rfind("}")

        if start == -1 or end == -1 or end <= start:
            raise ValueError(f"LLM did not return a JSON object: {raw}")

        json_text = text[start : end + 1]

        return json.loads(json_text)

    @staticmethod
    def _normalize_decision(decision: PlannerDecision) -> PlannerDecision:
        task_type = decision.task_type.strip().lower()
        next_agent = decision.next_agent.strip().lower()

        allowed_task_types = {"code_answer", "general"}
        allowed_next_agents = {"code", "none"}

        if task_type not in allowed_task_types:
            task_type = "general"

        if next_agent not in allowed_next_agents:
            next_agent = "none"

        if task_type == "code_answer":
            next_agent = "code"

        if next_agent == "code":
            task_type = "code_answer"

        return PlannerDecision(
            task_type=task_type,
            next_agent=next_agent,
            reason=decision.reason.strip() or "No reason provided.",
            rewritten_request=decision.rewritten_request.strip(),
        )

    def _fallback_decision(
        self,
        user_request: str,
        error: str,
    ) -> PlannerDecision:
        q = user_request.lower()

        code_keywords = {
            "code",
            "codebase",
            "implementation",
            "implemented",
            "function",
            "class",
            "method",
            "module",
            "file",
            "where is",
            "where does",
            "explain how",
            "agentloop",
            "toolruntime",
            "evidencestore",
            "engineeredrag",
            "subprocess",
            "chroma",
            "worker",
            "cli",
            "intent router",
            "permissionchecker",
            "contextmanager",
            "tracestore",
            "paperworkflowrunner",
            "codeworkflowrunner",
        }

        chinese_code_keywords = {
            "代码",
            "源码",
            "实现",
            "在哪里",
            "在哪",
            "函数",
            "类",
            "方法",
            "模块",
            "文件",
            "调用链",
            "执行流程",
            "工作流",
            "怎么实现",
            "如何实现",
            "代码里",
            "项目里",
        }

        if any(keyword in q for keyword in code_keywords) or any(
            keyword in user_request for keyword in chinese_code_keywords
        ):
            return PlannerDecision(
                task_type="code_answer",
                next_agent="code",
                reason=(
                    "Fallback selected code agent because the request appears "
                    f"to ask about code implementation. Planner error: {error}"
                ),
                rewritten_request=user_request,
            )

        return PlannerDecision(
            task_type="general",
            next_agent="none",
            reason=(
                "Fallback could not identify a specialized subagent. "
                f"Planner error: {error}"
            ),
            rewritten_request=user_request,
        )