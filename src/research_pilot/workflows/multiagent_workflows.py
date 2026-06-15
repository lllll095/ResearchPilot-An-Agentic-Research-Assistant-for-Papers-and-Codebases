# src/research_pilot/workflows/multiagent_workflows.py

from rich.console import Console

from research_pilot.conversation.session import ConversationSession
from research_pilot.core.llm_client import OpenAICompatibleLLMClient
from research_pilot.core.state import AgentState
from research_pilot.multiagent import ResearchPilotBlackboard, SubAgentInput
from research_pilot.multiagent.subagents import (
    CodeSubAgent,
    PaperSubAgent,
    PlannerSubAgent,
    ReviewerSubAgent,
)
from research_pilot.workflows.code_workflows import CodeWorkflowRunner
from research_pilot.workflows.paper_workflows import PaperWorkflowRunner


class MultiAgentWorkflowRunner:
    """Minimal multi-agent workflow runner.

    Current flow:

        blackboard
          -> LLM PlannerSubAgent
          -> CodeSubAgent or PaperSubAgent
          -> final answer

    This version validates the subagent and blackboard architecture before
    adding WriterSubAgent and ReviewerSubAgent.
    """

    def __init__(
        self,
        code_workflow_runner: CodeWorkflowRunner,
        paper_workflow_runner: PaperWorkflowRunner,
        llm_client: OpenAICompatibleLLMClient,
        console: Console | None = None,
    ):
        self.code_workflow_runner = code_workflow_runner
        self.paper_workflow_runner = paper_workflow_runner
        self.llm_client = llm_client
        self.console = console or Console()

        self.planner = PlannerSubAgent(llm_client=self.llm_client)
        self.code_agent = CodeSubAgent(runner=self.code_workflow_runner)
        self.paper_agent = PaperSubAgent(runner=self.paper_workflow_runner)
        self.reviewer = ReviewerSubAgent(llm_client=self.llm_client)

    def answer(
        self,
        user_request: str,
        session: ConversationSession | None = None,
    ) -> AgentState:
        """Run the minimal multi-agent workflow and return an AgentState."""

        blackboard = ResearchPilotBlackboard.from_session(
            user_request=user_request,
            session=session,
        )

        planner_output = self.planner.run(
            SubAgentInput(
                blackboard=blackboard,
                instruction=user_request,
            )
        )

        decision = planner_output.updates.get("planner_decision", {})
        next_agent = decision.get("next_agent")

        source_agent = "none"

        if next_agent == "code":
            final_answer = self._run_code_agent(
                user_request=user_request,
                blackboard=blackboard,
                decision=decision,
            )
            source_agent = "code"
        elif next_agent == "paper":
            final_answer = self._run_paper_agent(
                user_request=user_request,
                blackboard=blackboard,
                decision=decision,
            )
            source_agent = "paper"
        else:
            final_answer = (
                "The multi-agent runner could not select a specialized subagent.\n\n"
                "Current available subagents: code, paper.\n\n"
                f"Planner decision:\n{planner_output.content}"
            )

        review_output = self._run_reviewer(
            blackboard=blackboard,
            candidate_answer=final_answer,
            source_agent=source_agent,
        )
        state = AgentState(user_goal=user_request)
        state.final_answer = final_answer

        self._attach_metadata(
            state=state,
            key="blackboard",
            value=blackboard.model_dump(),
        )
        self._attach_metadata(
            state=state,
            key="planner_output",
            value=planner_output.model_dump(),
        )
        self._attach_metadata(
            state=state,
            key="review_output",
            value=review_output.model_dump(),
        )

        return state

    def _run_code_agent(
        self,
        user_request: str,
        blackboard: ResearchPilotBlackboard,
        decision: dict,
    ) -> str:
        code_output = self.code_agent.run(
            SubAgentInput(
                blackboard=blackboard,
                instruction=user_request,
                metadata={
                    "planner_decision": decision,
                },
            )
        )

        if not code_output.success:
            return (
                "CodeSubAgent failed.\n\n"
                f"{code_output.error}"
            )

        return code_output.content

    def _run_paper_agent(
        self,
        user_request: str,
        blackboard: ResearchPilotBlackboard,
        decision: dict,
    ) -> str:
        paper_output = self.paper_agent.run(
            SubAgentInput(
                blackboard=blackboard,
                instruction=user_request,
                metadata={
                    "planner_decision": decision,
                },
            )
        )

        if not paper_output.success:
            return (
                "PaperSubAgent failed.\n\n"
                f"{paper_output.error}"
            )

        return paper_output.content

    def _run_reviewer(
        self,
        blackboard: ResearchPilotBlackboard,
        candidate_answer: str,
        source_agent: str,
    ):
        """Run ReviewerSubAgent on the candidate answer.

        The first version records review results but does not rewrite the answer.
        """

        return self.reviewer.run(
            SubAgentInput(
                blackboard=blackboard,
                instruction="Review the candidate answer.",
                metadata={
                    "candidate_answer": candidate_answer,
                    "source_agent": source_agent,
                },
            )
        )

    @staticmethod
    def _attach_metadata(
        state: AgentState,
        key: str,
        value,
    ) -> None:
        """Attach metadata only if AgentState supports metadata."""

        if hasattr(state, "metadata") and isinstance(state.metadata, dict):
            state.metadata[key] = value