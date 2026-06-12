from research_pilot.agents.code_answer_writer_agent import CodeAnswerWriterAgent
from research_pilot.core.evidence import EvidenceItem, EvidenceType
from research_pilot.core.llm_client import OpenAICompatibleLLMClient
from research_pilot.core.observation import Observation
from research_pilot.core.tool import BaseTool


class WriteCodeAnswerTool(BaseTool):
    """Write a codebase answer using code evidence in the EvidenceStore."""

    name = "write_code_answer"
    description = (
        "Write a grounded answer about the codebase using previously collected "
        "code evidence from code_map, code_search, and code_read."
    )

    def __init__(self, llm_client: OpenAICompatibleLLMClient | None = None):
        self.llm_client = llm_client

    def run(self, tool_input: dict, state=None) -> Observation:
        question = tool_input.get("question", "")
        max_evidence_items = int(tool_input.get("max_evidence_items", 12))
        max_chars_per_item = int(tool_input.get("max_chars_per_item", 4000))

        if not question:
            return Observation(
                success=False,
                content="Missing input: question",
                error="MissingQuestion",
            )

        if state is None:
            return Observation(
                success=False,
                content="write_code_answer requires AgentState.",
                error="MissingState",
            )

        try:
            llm_client = self.llm_client or OpenAICompatibleLLMClient.from_settings()

            writer = CodeAnswerWriterAgent(llm_client=llm_client)
            answer = writer.write_answer(
                question=question,
                evidence_store=state.evidence_store,
                max_evidence_items=max_evidence_items,
                max_chars_per_item=max_chars_per_item,
            )

            state.evidence_store.add(
                EvidenceItem(
                    evidence_type=EvidenceType.CODE,
                    source=f"write_code_answer:{question}",
                    content=answer,
                    metadata={
                        "question": question,
                        "max_evidence_items": max_evidence_items,
                        "max_chars_per_item": max_chars_per_item,
                    },
                )
            )

            return Observation(
                success=True,
                content=answer,
                metadata={
                    "question": question,
                },
            )

        except Exception as exc:
            return Observation(
                success=False,
                content=(
                    "Failed to write code answer.\n"
                    f"Error type: {type(exc).__name__}\n"
                    f"Error message: {exc}"
                ),
                error="WriteCodeAnswerFailed",
            )