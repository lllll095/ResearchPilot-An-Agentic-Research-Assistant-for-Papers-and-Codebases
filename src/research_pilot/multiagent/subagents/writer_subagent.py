# src/research_pilot/multiagent/subagents/writer_subagent.py

from research_pilot.core.llm_client import OpenAICompatibleLLMClient
from research_pilot.multiagent.base_subagent import (
    BaseSubAgent,
    SubAgentInput,
    SubAgentOutput,
)


class WriterSubAgent(BaseSubAgent):
    """Rewrite a candidate answer using reviewer feedback and blackboard context."""

    name = "writer"
    description = "Rewrite final answers based on review feedback."

    def __init__(self, llm_client: OpenAICompatibleLLMClient):
        self.llm_client = llm_client

    def run(self, agent_input: SubAgentInput) -> SubAgentOutput:
        blackboard = agent_input.blackboard

        candidate_answer = agent_input.metadata.get("candidate_answer", "")
        review_result = agent_input.metadata.get("review_result", {})
        source_agent = agent_input.metadata.get("source_agent", "unknown")

        if not candidate_answer.strip():
            return SubAgentOutput(
                agent_name=self.name,
                success=False,
                content="",
                error="WriterSubAgent received an empty candidate answer.",
            )

        try:
            rewritten = self._rewrite(
                user_request=blackboard.user_request,
                blackboard_context=blackboard.compact_context(),
                candidate_answer=candidate_answer,
                review_result=review_result,
                source_agent=source_agent,
            )

            blackboard.add_note(
                author=self.name,
                content="WriterSubAgent rewrote the candidate answer using reviewer feedback.",
                metadata={
                    "source_agent": source_agent,
                    "review_result": review_result,
                },
            )

            return SubAgentOutput(
                agent_name=self.name,
                success=True,
                content=rewritten,
                updates={
                    "rewritten_answer": rewritten,
                },
            )

        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"

            blackboard.add_note(
                author=self.name,
                content=f"WriterSubAgent failed: {error}",
                metadata={
                    "source_agent": source_agent,
                    "review_result": review_result,
                },
            )

            return SubAgentOutput(
                agent_name=self.name,
                success=False,
                content="",
                error=error,
            )

    def _rewrite(
        self,
        user_request: str,
        blackboard_context: str,
        candidate_answer: str,
        review_result: dict,
        source_agent: str,
    ) -> str:
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

Reviewer feedback:
{review_result}

Candidate answer:
{candidate_answer}

Rewrite the answer.
""",
            },
        ]

        return self.llm_client.complete(messages).strip()

    def _system_prompt(self) -> str:
        return """You are the WriterSubAgent in a multi-agent research assistant.

Your job is to rewrite a candidate final answer using reviewer feedback.

Rules:
- Answer the original user request directly.
- Use the same language as the user request when possible.
- Use only information supported by the shared blackboard context and candidate answer.
- Do not invent files, citations, papers, tools, or implementation details.
- If evidence is incomplete, clearly state the limitation.
- Address the reviewer feedback.
- Preserve useful structure such as headings, file paths, citations, and bullet points.
- Do not mention internal multi-agent mechanics unless needed.
- Output only the rewritten final answer in markdown.
"""