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
            "Task type selected by the planner. Supported values: "
            "code_answer, paper_answer, paper_research, general."
        )
    )
    next_agent: str = Field(
        description=(
            "Next subagent to run. Supported values: code, paper, both, none."
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
        context = blackboard.compact_context(for_subagent="planner")

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

2. paper
- Use this for paper, literature, academic research, evidence-based answers,
  paper collection, literature review, survey, related work, and research reports.
- The paper agent can answer from existing indexed papers, but it can also run
  an adaptive local-first paper research workflow: retrieve local evidence first,
  collect/download/index new papers if evidence is insufficient, then answer.
- Chinese triggers include: 论文, 文献, 综述, 调研, 找论文, 搜论文, 下载论文,
  相关工作, 课题组汇报, 生成报告.

3. none
- Use this only when no available specialized subagent can handle the request.

You must return exactly one JSON object.
Do not use markdown.
Do not wrap the JSON in code fences.
Do not include explanations outside JSON.

JSON schema:

{
  "task_type": "code_answer | paper_answer | paper_research | general",
  "next_agent": "code | paper | both | none",
  "reason": "short reason",
  "rewritten_request": "optional rewritten request"
}

Rules:
- For codebase implementation questions, choose task_type="code_answer" and next_agent="code".
- If the user asks in Chinese about 代码, 源码, 实现, 函数, 类, 模块, 调用链, 工作流, or 在哪里, choose the code agent.
- For direct questions about already indexed/downloaded papers or paper evidence, choose task_type="paper_answer" and next_agent="paper".
- For broader requests asking to research a topic, write a report, collect evidence, summarize literature, or find papers if needed, choose task_type="paper_research" and next_agent="paper".
- If the user asks in Chinese about 论文, 文献, 综述, 研究, 引用, 课题组汇报, or 学术资料, choose the paper agent.
- If the user uses references like "it", "that", "刚才那个", use the blackboard context to rewrite the request if possible.
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

        allowed_task_types = {
            "code_answer",
            "paper_answer",
            "paper_research",
            "general",
        }
        allowed_next_agents = {"code", "paper", "both", "none"}

        if task_type not in allowed_task_types:
            task_type = "general"

        if next_agent not in allowed_next_agents:
            next_agent = "none"

        if task_type == "code_answer":
            next_agent = "code"

        if task_type in {"paper_answer", "paper_research"}:
            next_agent = "paper"

        if next_agent == "code":
            task_type = "code_answer"

        if next_agent == "paper" and task_type not in {"paper_answer", "paper_research"}:
            task_type = "paper_answer"

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

        paper_keywords = {
            "paper",
            "papers",
            "literature",
            "academic",
            "reference",
            "references",
            "citation",
            "citations",
            "research",
            "survey",
            "review",
            "report",
            "article",
            "publication",
            "study",
        }

        chinese_paper_keywords = {
            "论文",
            "文献",
            "综述",
            "研究",
            "引用",
            "报告",
            "学术",
            "课题组",
            "汇报",
            "资料",
        }

        # 1. Code fallback first.
        # This is important because some code-related names may contain words
        # such as PaperWorkflowRunner. Those should still be routed to code.
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

        # 2. Paper fallback second.
        if any(keyword in q for keyword in paper_keywords) or any(
            keyword in user_request for keyword in chinese_paper_keywords
        ):
            task_type = "paper_research" if (
                "report" in q
                or "survey" in q
                or "review" in q
                or "综述" in user_request
                or "报告" in user_request
                or "汇报" in user_request
                or "课题组" in user_request
            ) else "paper_answer"

            return PlannerDecision(
                task_type=task_type,
                next_agent="paper",
                reason=(
                    "Fallback selected paper agent because the request appears "
                    f"to ask about papers or literature. Planner error: {error}"
                ),
                rewritten_request=user_request,
            )

        # 3. General fallback last.
        return PlannerDecision(
            task_type="general",
            next_agent="none",
            reason=(
                "Fallback could not identify a specialized subagent. "
                f"Planner error: {error}"
            ),
            rewritten_request=user_request,
        )