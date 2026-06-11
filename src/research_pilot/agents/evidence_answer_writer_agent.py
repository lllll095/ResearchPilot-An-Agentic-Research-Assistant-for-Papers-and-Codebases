from research_pilot.core.evidence import EvidenceStore
from research_pilot.core.llm_client import OpenAICompatibleLLMClient


class EvidenceAnswerWriterAgent:
    """Write citation-aware answers from collected evidence.

    This agent borrows the answer style from the old EngineeredRAG:
    - use only retrieved evidence
    - provide concise answer
    - provide grounded explanation
    - list sources
    - mention limitations
    """

    def __init__(self, llm_client: OpenAICompatibleLLMClient):
        self.llm_client = llm_client

    def write_answer(
        self,
        question: str,
        evidence_store: EvidenceStore,
        max_evidence_items: int = 6,
        max_chars_per_item: int = 3500,
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

Retrieved evidence:
{evidence_text}
""",
            },
        ]

        return self.llm_client.complete(messages).strip()

    def _system_prompt(self) -> str:
        return """You are a careful citation-aware research assistant.

You must answer the question using only the retrieved evidence provided by the user.

Important rules:
- Do not invent unsupported claims.
- Do not cite sources that are not present in the evidence.
- Preserve source identifiers such as [Source 1], [Source 2], file names, page numbers, and chunk IDs when available.
- If the evidence is insufficient, explicitly say what is missing.
- Prefer concrete claims grounded in specific retrieved chunks.
- Do not mention internal tool names unless necessary.
- Output markdown.

Use exactly this structure:

## Answer

Give a concise direct answer.

## Explanation

Explain the answer using the retrieved evidence. Include source markers such as [Source 1] or file/page/chunk references when available.

## Sources Used

List the sources you used. For each source, include source id, file name, page, and chunk id if available.

## Limitations

State what the retrieved evidence does not fully answer.
"""