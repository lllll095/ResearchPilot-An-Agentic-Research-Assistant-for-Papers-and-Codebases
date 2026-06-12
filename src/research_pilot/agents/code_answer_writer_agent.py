from research_pilot.core.evidence import EvidenceStore
from research_pilot.core.llm_client import OpenAICompatibleLLMClient


class CodeAnswerWriterAgent:
    """Write grounded answers about the codebase using collected code evidence."""

    def __init__(self, llm_client: OpenAICompatibleLLMClient):
        self.llm_client = llm_client

    def write_answer(
        self,
        question: str,
        evidence_store: EvidenceStore,
        max_evidence_items: int = 12,
        max_chars_per_item: int = 4000,
    ) -> str:
        evidence_text = evidence_store.render(
            max_items=max_evidence_items,
            max_chars_per_item=max_chars_per_item,
        )

        messages = [
            {
                "role": "system",
                "content": self._system_prompt(),
            },
            {
                "role": "user",
                "content": f"""Question:
{question}

Code evidence:
{evidence_text}
""",
            },
        ]

        return self.llm_client.complete(messages).strip()

    def _system_prompt(self) -> str:
        return """You are a careful codebase explanation assistant.

You must answer using only the provided code evidence.

Rules:
- Answer in the same language as the user's question.
- Do not invent implementation details that are not supported by the code evidence.
- Cite file paths and line numbers whenever available.
- Explain the execution flow clearly.
- If evidence is insufficient, say what is missing.
- Do not modify code.
- Output markdown.

Use this structure exactly:

## Answer

Give a concise direct answer.

## Code Flow

Explain the main execution flow step by step.

## Key Files and Responsibilities

List important files/classes/functions and what each does.

## Evidence Used

List the code evidence you used, including file paths and line numbers when available.

## Limitations

State what cannot be concluded from the provided evidence.
"""