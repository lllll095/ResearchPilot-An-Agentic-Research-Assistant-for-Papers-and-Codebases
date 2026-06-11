from research_pilot.agents.task_summarizer_agent import TaskSummarizerAgent
from research_pilot.core.evidence import EvidenceItem, EvidenceType
from research_pilot.core.llm_client import OpenAICompatibleLLMClient
from research_pilot.core.observation import Observation
from research_pilot.core.tool import BaseTool, ToolSpec


class SummarizeEvidenceTool(BaseTool):
    name = "summarize_evidence"
    description = "Summarize collected evidence for a research task."

    def __init__(self, llm_client: OpenAICompatibleLLMClient | None = None):
        self.summarizer = TaskSummarizerAgent(llm_client=llm_client)

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "task": "Research task or question to summarize evidence for.",
                "max_evidence_items": "Optional number of evidence items to use. Default is 6.",
                "max_chars_per_item": "Optional max characters per evidence item. Default is 2500.",
            },
        )

    def run(self, tool_input: dict, state=None) -> Observation:
        if state is None:
            return Observation(
                success=False,
                content="SummarizeEvidenceTool requires AgentState.",
                error="MissingState",
            )

        task = tool_input.get("task", state.user_goal)
        max_evidence_items = int(tool_input.get("max_evidence_items", 6))
        max_chars_per_item = int(tool_input.get("max_chars_per_item", 2500))

        summary = self.summarizer.summarize(
            task=task,
            evidence_store=state.evidence_store,
            max_evidence_items=max_evidence_items,
            max_chars_per_item=max_chars_per_item,
        )

        state.evidence_store.add(
            EvidenceItem(
                evidence_type=EvidenceType.NOTE,
                source=f"summarize_evidence:{task}",
                content=summary,
                metadata={
                    "task": task,
                    "max_evidence_items": max_evidence_items,
                },
            )
        )

        return Observation(
            success=True,
            content=summary,
            metadata={
                "task": task,
                "max_evidence_items": max_evidence_items,
            },
        )