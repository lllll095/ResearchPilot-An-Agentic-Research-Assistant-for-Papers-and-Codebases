# src/research_pilot/multiagent/subagents/reviewer_subagent.py

import json
from typing import Any

from pydantic import BaseModel, Field

from research_pilot.core.llm_client import OpenAICompatibleLLMClient
from research_pilot.multiagent.base_subagent import (
    BaseSubAgent,
    SubAgentInput,
    SubAgentOutput,
)


class ReviewResult(BaseModel):
    """Structured review result for a candidate answer."""

    passed: bool = Field(
        description="Whether the answer is acceptable."
    )
    confidence: str = Field(
        description="One of: high, medium, low."
    )
    issues: list[str] = Field(
        default_factory=list,
        description="Problems found in the answer.",
    )
    missing_evidence: list[str] = Field(
        default_factory=list,
        description="Important evidence that seems missing.",
    )
    unsupported_claims: list[str] = Field(
        default_factory=list,
        description="Claims that are not supported by the blackboard evidence.",
    )
    suggestions: list[str] = Field(
        default_factory=list,
        description="Concrete suggestions for improving the answer.",
    )


class ReviewerSubAgent(BaseSubAgent):
    """Review final answers against the shared blackboard context."""

    name = "reviewer"
    description = "Review whether a candidate answer is grounded and complete."

    def __init__(self, llm_client: OpenAICompatibleLLMClient):
        self.llm_client = llm_client

    def run(self, agent_input: SubAgentInput) -> SubAgentOutput:
        blackboard = agent_input.blackboard
        candidate_answer = agent_input.metadata.get("candidate_answer", "")
        source_agent = agent_input.metadata.get("source_agent", "unknown")

        if not candidate_answer.strip():
            result = ReviewResult(
                passed=False,
                confidence="high",
                issues=["Candidate answer is empty."],
                suggestions=["Run a specialist subagent before reviewing."],
            )

            blackboard.add_note(
                author=self.name,
                content="Reviewer rejected an empty candidate answer.",
                metadata=result.model_dump(),
            )

            return SubAgentOutput(
                agent_name=self.name,
                success=True,
                content=result.model_dump_json(indent=2),
                updates={
                    "review_result": result.model_dump(),
                },
            )

        try:
            result = self._review(
                user_request=blackboard.user_request,
                blackboard_context=blackboard.compact_context(),
                candidate_answer=candidate_answer,
                source_agent=source_agent,
            )

        except Exception as exc:
            # Reviewer should not break the whole multi-agent workflow.
            # If review fails, we record the failure and let the original answer pass.
            result = ReviewResult(
                passed=True,
                confidence="low",
                issues=[
                    (
                        "Reviewer LLM failed, so the workflow kept the original "
                        "answer without a reliable review."
                    )
                ],
                suggestions=[
                    f"Reviewer error: {type(exc).__name__}: {exc}",
                ],
            )

        blackboard.add_note(
            author=self.name,
            content=(
                f"Review completed. passed={result.passed}, "
                f"confidence={result.confidence}."
            ),
            metadata=result.model_dump(),
        )

        return SubAgentOutput(
            agent_name=self.name,
            success=True,
            content=result.model_dump_json(indent=2),
            updates={
                "review_result": result.model_dump(),
            },
        )

    def _review(
        self,
        user_request: str,
        blackboard_context: str,
        candidate_answer: str,
        source_agent: str,
    ) -> ReviewResult:
        messages = [
            {
                "role": "system",
                "content": self._system_prompt(),
            },
            {
                "role": "user",
                "content": f"""User request:
{user_request}

Source agent:
{source_agent}

Shared blackboard context:
{blackboard_context}

Candidate answer:
{candidate_answer}
""",
            },
        ]

        raw = self.llm_client.complete(messages).strip()
        payload = self._parse_json(raw)

        result = ReviewResult.model_validate(payload)
        return self._normalize_result(result)

    def _system_prompt(self) -> str:
        return """You are the ReviewerSubAgent in a multi-agent research assistant.

Your job is to review a candidate answer using the shared blackboard context.

You must not answer the user directly.
You must not rewrite the answer.
You only judge whether the candidate answer is acceptable.

Check:
- Is the answer relevant to the user request?
- Is the answer grounded in the blackboard context?
- Does it mention files, tools, papers, or evidence that are not supported?
- Does it honestly state limitations when evidence is incomplete?
- For code questions, does it cite or discuss concrete files/classes/functions when available?
- For paper questions, does it avoid unsupported claims?

You must return exactly one JSON object.
Do not use markdown.
Do not wrap the JSON in code fences.
Do not include explanations outside JSON.

JSON schema:

{
  "passed": true,
  "confidence": "high | medium | low",
  "issues": ["issue 1"],
  "missing_evidence": ["missing evidence 1"],
  "unsupported_claims": ["unsupported claim 1"],
  "suggestions": ["suggestion 1"]
}

Guidelines:
- passed=true means the answer is usable.
- passed=false means the answer is seriously incomplete, unsupported, or misleading.
- Do not fail an answer only because it is not perfect.
- Fail the answer if it claims details that are not supported by available evidence.
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
    def _normalize_result(result: ReviewResult) -> ReviewResult:
        confidence = result.confidence.strip().lower()

        if confidence not in {"high", "medium", "low"}:
            confidence = "low"

        return ReviewResult(
            passed=bool(result.passed),
            confidence=confidence,
            issues=result.issues,
            missing_evidence=result.missing_evidence,
            unsupported_claims=result.unsupported_claims,
            suggestions=result.suggestions,
        )