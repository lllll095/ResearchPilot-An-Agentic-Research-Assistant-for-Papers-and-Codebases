from research_pilot.core.evidence import EvidenceStore
from research_pilot.core.llm_client import OpenAICompatibleLLMClient


class TaskSummarizerAgent:
    """Summarize collected evidence for a research task.

    This is similar in spirit to the Task Summarizer in Hello Agents Chapter 14.
    """

    def __init__(self, llm_client: OpenAICompatibleLLMClient | None = None):
        self.llm_client = llm_client

    def summarize(
        self,
        task: str,
        evidence_store: EvidenceStore,
        max_evidence_items: int = 6,
        max_chars_per_item: int = 2500,
    ) -> str:
        evidence_text = evidence_store.render(max_items=max_evidence_items, max_chars_per_item=max_chars_per_item)

        if self.llm_client is None:
            return self._fallback_summary(task, evidence_text)

        messages = [
            {
                "role": "system",
                "content": self._system_prompt(),
            },
            {
                "role": "user",
                "content": f"""Research task:
{task}

Evidence:
{evidence_text}
""",
            },
        ]

        try:
            return self.llm_client.complete(messages).strip()
        except Exception:
            return self._fallback_summary(task, evidence_text)

    def _system_prompt(self) -> str:
        return """You are a research task summarizer.

Your job is to summarize collected evidence into a concise, grounded research note.

Rules:
- Use only the provided evidence.
- Do not invent sources.
- Keep the summary structured.
- Mention limitations if evidence is weak.
- Output markdown.

Suggested format:

## Task Summary

## Key Findings

## Useful Evidence

## Limitations
"""

    def _fallback_summary(self, task: str, evidence_text: str) -> str:
        return f"""## Task Summary

Task: {task}

## Evidence Snapshot

{evidence_text}

## Limitations

This is a fallback summary generated without an LLM summarizer.
"""