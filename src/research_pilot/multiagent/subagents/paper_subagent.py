# src/research_pilot/multiagent/subagents/paper_subagent.py

from research_pilot.core.state import AgentState
from research_pilot.multiagent.base_subagent import (
    BaseSubAgent,
    SubAgentInput,
    SubAgentOutput,
)
from research_pilot.workflows.paper_workflows import PaperWorkflowRunner


class PaperSubAgent(BaseSubAgent):
    """Subagent for paper QA and paper research tasks.

    This subagent reuses existing deterministic paper workflows.
    It does not directly implement search, download, indexing, or answer writing.
    """

    name = "paper"
    description = "Answer paper-related questions or run paper research workflows."

    def __init__(
        self,
        runner: PaperWorkflowRunner,
        max_papers: int = 3,
        force_download: bool = False,
        save_report: bool = False,
    ):
        self.runner = runner
        self.max_papers = max_papers
        self.force_download = force_download
        self.save_report = save_report

    def run(self, agent_input: SubAgentInput) -> SubAgentOutput:
        blackboard = agent_input.blackboard

        planner_decision = agent_input.metadata.get("planner_decision", {})
        rewritten_request = planner_decision.get("rewritten_request") or ""
        task_type = planner_decision.get("task_type") or "paper_answer"

        question = self._build_paper_question(
            original_request=blackboard.user_request,
            instruction=agent_input.instruction,
            rewritten_request=rewritten_request,
        )

        try:
            if task_type == "paper_research":
                state = self.runner.paper_research(
                    question=question,
                    max_papers=self.max_papers,
                    force_download=self.force_download,
                    save_report=self.save_report,
                )
            else:
                state = self.runner.paper_answer(
                    question=question,
                    save_report=self.save_report,
                )

            blackboard.merge_agent_state(state)

            answer = state.final_answer or ""

            blackboard.add_note(
                author=self.name,
                content="PaperSubAgent completed the paper workflow.",
                metadata={
                    "task_type": task_type,
                    "num_steps": len(state.steps),
                    "question": question,
                    "max_papers": self.max_papers,
                    "force_download": self.force_download,
                    "save_report": self.save_report,
                },
            )

            return SubAgentOutput(
                agent_name=self.name,
                success=True,
                content=answer,
                updates={
                    "final_answer": answer,
                    "agent_state": self._state_summary(state),
                },
            )

        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"

            blackboard.add_note(
                author=self.name,
                content=f"PaperSubAgent failed: {error}",
                metadata={
                    "task_type": task_type,
                    "question": question,
                },
            )

            return SubAgentOutput(
                agent_name=self.name,
                success=False,
                content="",
                error=error,
            )

    def _build_paper_question(
        self,
        original_request: str,
        instruction: str = "",
        rewritten_request: str = "",
    ) -> str:
        """Build a robust paper question.

        The original request may contain important paper/topic terms.
        The planner rewrite may clarify the task, but should not erase
        the user's original wording.
        """

        sections: list[str] = []

        if original_request.strip():
            sections.append(
                "Original user request:\n"
                f"{original_request.strip()}"
            )

        if instruction.strip() and instruction.strip() != original_request.strip():
            sections.append(
                "Subagent instruction:\n"
                f"{instruction.strip()}"
            )

        if rewritten_request.strip() and rewritten_request.strip() not in {
            original_request.strip(),
            instruction.strip(),
        }:
            sections.append(
                "Planner rewritten request:\n"
                f"{rewritten_request.strip()}"
            )

        sections.append(
            "Paper task instruction:\n"
            "Preserve important research topic terms, paper names, method names, "
            "and citation-related requirements from the original request."
        )

        return "\n\n".join(sections)

    @staticmethod
    def _state_summary(state: AgentState) -> dict:
        evidence_store = getattr(state, "evidence_store", None)
        evidence_items = getattr(evidence_store, "items", []) if evidence_store else []

        return {
            "final_answer_preview": (state.final_answer or "")[:500],
            "num_steps": len(state.steps),
            "num_evidence_items": len(evidence_items),
        }