# src/research_pilot/multiagent/subagents/code_subagent.py

from research_pilot.core.state import AgentState
from research_pilot.multiagent.base_subagent import (
    BaseSubAgent,
    SubAgentInput,
    SubAgentOutput,
)
from research_pilot.workflows.code_workflows import CodeWorkflowRunner


class CodeSubAgent(BaseSubAgent):
    """Subagent for codebase understanding tasks.

    This subagent reuses the existing deterministic code-answer workflow.
    It does not directly implement code search or code reading itself.
    """

    name = "code"
    description = "Answer codebase implementation questions."

    def __init__(
        self,
        runner: CodeWorkflowRunner,
        code_path: str = "src/research_pilot",
        max_results: int = 20,
        max_files_to_read: int = 5,
    ):
        self.runner = runner
        self.code_path = code_path
        self.max_results = max_results
        self.max_files_to_read = max_files_to_read

    def run(self, agent_input: SubAgentInput) -> SubAgentOutput:
        blackboard = agent_input.blackboard

        planner_decision = agent_input.metadata.get("planner_decision", {})
        rewritten_request = planner_decision.get("rewritten_request") or ""

        question = self._build_code_question(
            original_request=blackboard.user_request,
            instruction=agent_input.instruction,
            rewritten_request=rewritten_request,
        )

        try:
            state = self.runner.code_answer(
                question=question,
                path=self.code_path,
                max_results=self.max_results,
                max_files_to_read=self.max_files_to_read,
            )

            blackboard.merge_agent_state(state)

            answer = state.final_answer or ""

            blackboard.add_note(
                author=self.name,
                content="CodeSubAgent completed the code-answer workflow.",
                metadata={
                    "code_path": self.code_path,
                    "num_steps": len(state.steps),
                    "question": question,
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
                content=f"CodeSubAgent failed: {error}",
                metadata={
                    "code_path": self.code_path,
                    "question": question,
                },
            )

            return SubAgentOutput(
                agent_name=self.name,
                success=False,
                content="",
                error=error,
            )
        
    def _build_code_question(
        self,
        original_request: str,
        instruction: str = "",
        rewritten_request: str = "",
    ) -> str:
        """Build a robust code question for retrieval.

        The original request often contains important exact symbols such as
        AgentLoop, ToolRuntime, CodeWorkflowRunner, or file names. The planner
        rewrite may improve intent clarity, but it should not replace the original
        query for code retrieval.
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
            "Code retrieval instruction:\n"
            "Preserve exact class names, function names, file names, and module names "
            "from the original request when searching the codebase."
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