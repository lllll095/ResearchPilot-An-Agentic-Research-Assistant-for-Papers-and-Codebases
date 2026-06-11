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
        evidence_blocks: list[dict] | None = None,
        max_evidence_items: int = 6,
        max_chars_per_item: int = 3500,
    ) -> str:
        if evidence_blocks:
            evidence_text = self._format_evidence_blocks(
                evidence_blocks=evidence_blocks,
                max_chars_per_block=max_chars_per_item,
            )
        else:
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
    
    def _format_evidence_blocks(
        self,
        evidence_blocks: list[dict],
        max_chars_per_block: int = 3500,
    ) -> str:
        blocks = []

        for block in evidence_blocks:
            source_id = block.get("source_id", "unknown")
            file = block.get("file", "unknown")
            page = block.get("page", "unknown")
            chunk_id = block.get("chunk_id", "unknown")
            chunk_type = block.get("chunk_type", "unknown")
            vector_score = block.get("vector_score", "unknown")
            bm25_score = block.get("bm25_score", "unknown")
            reranker_score = block.get("reranker_score", "unknown")
            content = block.get("content", "")

            if len(content) > max_chars_per_block:
                content = content[:max_chars_per_block] + "\n[Source content truncated]"

            blocks.append(
                f"""[Source {source_id}]
    File: {file}
    Page: {page}
    Chunk ID: {chunk_id}
    Chunk Type: {chunk_type}
    Vector Score: {vector_score}
    BM25 Score: {bm25_score}
    Reranker Score: {reranker_score}

    Content:
    {content}
    """
            )

        return "\n\n".join(blocks)

    def _system_prompt(self) -> str:
        return """You are a careful citation-aware research assistant.

You must answer the question using only the retrieved evidence.

Strict rules:
- Use only the provided retrieved evidence.
- Do not invent unsupported claims.
- Every important claim must cite at least one source marker, such as [Source 1].
- If a claim cannot be supported by a source, do not include it.
- Preserve file names, page numbers, and chunk IDs in the Sources Used section.
- If the evidence is insufficient, explicitly say what is missing.
- Do not cite sources that are not present in the evidence.
- Output markdown.

Use exactly this structure:

## Answer

Give a concise direct answer. Include source markers for key claims.

## Architecture Breakdown

List the main architecture components as bullet points.
Every bullet must include at least one citation.

## Explanation

Explain how the components work together using the retrieved evidence.
Use source markers such as [Source 1], [Source 2].

## Sources Used

List every source you used in this format:
- [Source X] file name, page, chunk id: what it supports.

## Limitations

State what the retrieved evidence does not fully answer.
"""