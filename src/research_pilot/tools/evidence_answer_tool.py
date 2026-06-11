from research_pilot.agents.evidence_answer_writer_agent import EvidenceAnswerWriterAgent
from research_pilot.core.evidence import EvidenceItem, EvidenceType
from research_pilot.core.llm_client import OpenAICompatibleLLMClient
from research_pilot.core.observation import Observation
from research_pilot.core.tool import BaseTool, ToolSpec


class WriteEvidenceAnswerTool(BaseTool):
    name = "write_evidence_answer"
    description = "Write a citation-aware answer using the collected evidence."

    def __init__(self, llm_client: OpenAICompatibleLLMClient | None = None):
        self.llm_client = llm_client

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "question": "Question to answer using collected evidence.",
                "max_evidence_items": "Optional number of evidence items to use. Default is 6.",
                "max_chars_per_item": "Optional max characters per evidence item. Default is 3500.",
            },
        )
    
    def _collect_evidence_blocks(self, state) -> list[dict]:
        blocks = []

        for item in state.evidence_store.items:
            item_blocks = item.metadata.get("evidence_blocks")

            if isinstance(item_blocks, list):
                blocks.extend(item_blocks)

        return blocks

    def run(self, tool_input: dict, state=None) -> Observation:
        if state is None:
            return Observation(
                success=False,
                content="WriteEvidenceAnswerTool requires AgentState.",
                error="MissingState",
            )

        if self.llm_client is None:
            return Observation(
                success=False,
                content=(
                    "WriteEvidenceAnswerTool requires an LLM client. "
                    "Run with --policy llm or register this tool with llm_client."
                ),
                error="MissingLLMClient",
            )

        question = tool_input.get("question", state.user_goal)
        max_evidence_items = int(tool_input.get("max_evidence_items", 6))
        max_chars_per_item = int(tool_input.get("max_chars_per_item", 3500))

        writer = EvidenceAnswerWriterAgent(llm_client=self.llm_client)

        try:
            evidence_blocks = self._collect_evidence_blocks(state)

            answer = writer.write_answer(
                question=question,
                evidence_store=state.evidence_store,
                evidence_blocks=evidence_blocks,
                max_evidence_items=max_evidence_items,
                max_chars_per_item=max_chars_per_item,
            )
        except Exception as exc:
            return Observation(
                success=False,
                content=(
                    "Failed to write citation-aware evidence answer.\n"
                    f"Error type: {type(exc).__name__}\n"
                    f"Error message: {exc}"
                ),
                error="EvidenceAnswerWriterFailed",
            )

        state.evidence_store.add(
            EvidenceItem(
                evidence_type=EvidenceType.NOTE,
                source=f"write_evidence_answer:{question}",
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
                "max_evidence_items": max_evidence_items,
                "max_chars_per_item": max_chars_per_item,
            },
        )