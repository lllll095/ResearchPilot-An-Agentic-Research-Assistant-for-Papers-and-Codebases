# src/research_pilot/workflows/multiagent_graph_workflows.py

from typing import Any

from rich.console import Console

from research_pilot.conversation.session import ConversationSession
from research_pilot.core.llm_client import OpenAICompatibleLLMClient
from research_pilot.core.state import AgentState
from research_pilot.graph import (
    FunctionGraphNode,
    GraphNodeResult,
    GraphState,
    GraphWorkflowRunner,
)
from research_pilot.multiagent import ResearchPilotBlackboard, SubAgentInput
from research_pilot.multiagent.subagents import (
    CodeSubAgent,
    GeneralSubAgent,
    PaperSubAgent,
    PlannerSubAgent,
    ReviewerSubAgent,
    WriterSubAgent,
)
from research_pilot.workflows.code_workflows import CodeWorkflowRunner
from research_pilot.workflows.paper_workflows import PaperWorkflowRunner
from research_pilot.core.agent_loop import AgentLoop
from research_pilot.graph.policy import RetryPolicy

class MultiAgentGraphWorkflowRunner:
    """Graph-based multi-agent workflow runner.

    Current graph:

        prepare
          -> planner
          -> code / paper / final
          -> reviewer
          -> final / retry / writer
          -> code / paper
          -> reviewer
          -> writer
          -> final
    """

    def __init__(
        self,
        code_workflow_runner: CodeWorkflowRunner,
        paper_workflow_runner: PaperWorkflowRunner,
        llm_client: OpenAICompatibleLLMClient,
        general_agent_loop: AgentLoop | None = None,
        console: Console | None = None,
        retry_policy: RetryPolicy | None = None,
        max_graph_steps: int = 20,
    ):
        self.code_workflow_runner = code_workflow_runner
        self.paper_workflow_runner = paper_workflow_runner
        self.llm_client = llm_client
        self.console = console or Console()

        self.retry_policy = retry_policy or RetryPolicy()
        self.max_graph_steps = max_graph_steps

        self.planner = PlannerSubAgent(llm_client=self.llm_client)
        self.code_agent = CodeSubAgent(runner=self.code_workflow_runner)
        self.paper_agent = PaperSubAgent(runner=self.paper_workflow_runner)
        self.general_agent = GeneralSubAgent(
            agent_loop=general_agent_loop,
            llm_client=self.llm_client,
        )
        self.reviewer = ReviewerSubAgent(llm_client=self.llm_client)
        self.writer = WriterSubAgent(llm_client=self.llm_client)

    def answer(
        self,
        user_request: str,
        session: ConversationSession | None = None,
    ) -> AgentState:
        """Run the graph workflow and return an AgentState-compatible result."""

        graph = self._build_graph()

        graph_state = graph.run(
            user_request=user_request,
            initial_metadata={
                "session_obj": session,
                "session_id": session.session_id if session else None,
                "retry_count": 0,
            },
        )

        # Generate Mermaid diagram for traceability
        try:
            mermaid = graph.render_mermaid(graph_state)
            self.console.print("[dim]Graph execution path (Mermaid):[/dim]")
            self.console.print(mermaid)
            state.metadata["graph_mermaid"] = mermaid
        except Exception:
            pass

        state = AgentState(user_goal=user_request)
        state.final_answer = graph_state.final_answer

        self._attach_metadata(
            state=state,
            key="graph_state",
            value=self._sanitize_graph_state(graph_state),
        )

        # Keep compatibility with existing debug/eval/report helpers.
        metadata = self._sanitize_metadata(graph_state.metadata)

        for key in [
            "blackboard",
            "planner_output",
            "initial_specialist_output",
            "general_output",
            "review_output",
            "specialist_retry_outputs",
            "specialist_retry_review_outputs",
            "writer_output",
            "source_agent",
            "current_answer",
        ]:
            if key in metadata:
                self._attach_metadata(state=state, key=key, value=metadata[key])

        self._attach_metadata(
            state=state,
            key="visited_nodes",
            value=graph_state.visited_nodes,
        )

        return state

    def _build_graph(self) -> GraphWorkflowRunner:
        graph = GraphWorkflowRunner(
            start_node="prepare",
            max_steps=self.max_graph_steps,
            console=self.console,
            stop_on_node_error=True,
        )

        graph.add_node(FunctionGraphNode("prepare", self._prepare_node))
        graph.add_node(FunctionGraphNode("planner", self._planner_node))
        graph.add_node(FunctionGraphNode("code", self._code_node))
        graph.add_node(FunctionGraphNode("paper", self._paper_node))
        graph.add_node(FunctionGraphNode("general", self._general_node))

        # Parallel group: run code and paper specialists together
        graph.add_parallel_group(
            name="code_and_paper",
            sub_nodes=[
                FunctionGraphNode("code", self._code_node),
                FunctionGraphNode("paper", self._paper_node),
            ],
            description="Parallel: code and paper sub-agents",
        )
        graph.add_edge("code_and_paper", "reviewer")
        graph.add_node(FunctionGraphNode("reviewer", self._reviewer_node))
        graph.add_node(FunctionGraphNode("retry", self._retry_node))
        graph.add_node(FunctionGraphNode("writer", self._writer_node))
        graph.add_node(FunctionGraphNode("final", self._final_node))

        graph.add_edge("prepare", "planner")

        graph.add_conditional_edge("planner", self._route_after_planner)
        graph.add_edge("code", "reviewer")
        graph.add_edge("paper", "reviewer")
        graph.add_edge("general", "final")
        graph.add_conditional_edge("reviewer", self._route_after_review)
        graph.add_conditional_edge("retry", self._route_after_retry)
        graph.add_edge("writer", "final")

        return graph

    def _prepare_node(self, state: GraphState) -> GraphNodeResult:
        session = state.metadata.get("session_obj")

        blackboard = ResearchPilotBlackboard.from_session(
            user_request=state.user_request,
            session=session if isinstance(session, ConversationSession) else None,
        )

        return GraphNodeResult(
            success=True,
            updates={
                "blackboard": blackboard,
            },
            output_preview="Prepared blackboard.",
            metadata={
                "session_id": state.metadata.get("session_id"),
            },
        )

    def _planner_node(self, state: GraphState) -> GraphNodeResult:
        blackboard = self._blackboard(state)

        output = self.planner.run(
            SubAgentInput(
                blackboard=blackboard,
                instruction=state.user_request,
            )
        )

        decision = output.updates.get("planner_decision", {})

        return GraphNodeResult(
            success=output.success,
            updates={
                "planner_output": output.model_dump(),
                "planner_decision": decision,
            },
            error=output.error,
            output_preview=output.content[:1000],
            metadata={
                "next_agent": decision.get("next_agent"),
                "task_type": decision.get("task_type"),
            },
        )

    def _code_node(self, state: GraphState) -> GraphNodeResult:
        return self._run_specialist_node(
            state=state,
            source_agent="code",
            subagent=self.code_agent,
        )

    def _paper_node(self, state: GraphState) -> GraphNodeResult:
        return self._run_specialist_node(
            state=state,
            source_agent="paper",
            subagent=self.paper_agent,
        )
    
    def _general_node(self, state: GraphState) -> GraphNodeResult:
        blackboard = self._blackboard(state)

        output = self.general_agent.run(
            SubAgentInput(
                blackboard=blackboard,
                instruction=state.user_request,
                metadata={
                    "planner_decision": state.metadata.get("planner_decision") or {},
                },
            )
        )

        if output.success and output.content.strip():
            answer = output.content
        else:
            answer = (
                "The general fallback agent failed to answer the request.\n\n"
                f"Error: {output.error}"
            )

        return GraphNodeResult(
            success=output.success,
            updates={
                "blackboard": blackboard,
                "source_agent": "general",
                "current_answer": answer,
                "initial_specialist_output": output.model_dump(),
                "general_output": output.model_dump(),
            },
            error=output.error,
            output_preview=answer[:1000],
            metadata={
                "source_agent": "general",
            },
        )

    def _run_specialist_node(
        self,
        state: GraphState,
        source_agent: str,
        subagent,
    ) -> GraphNodeResult:
        blackboard = self._blackboard(state)
        decision = state.metadata.get("planner_decision") or {}
        instruction = state.metadata.get("current_instruction") or state.user_request

        output = subagent.run(
            SubAgentInput(
                blackboard=blackboard,
                instruction=instruction,
                metadata={
                    "planner_decision": decision,
                },
            )
        )

        candidate_answer = self._answer_from_specialist_output(
            specialist_output=output,
            source_agent=source_agent,
        )

        updates: dict[str, Any] = {
            "blackboard": blackboard,
            "source_agent": source_agent,
            "current_answer": candidate_answer,
            "current_instruction": "",
        }

        retry_count = int(state.metadata.get("retry_count", 0))

        if retry_count == 0:
            updates["initial_specialist_output"] = output.model_dump()
        else:
            retry_outputs = list(state.metadata.get("specialist_retry_outputs") or [])
            retry_outputs.append(output.model_dump())
            updates["specialist_retry_outputs"] = retry_outputs

        return GraphNodeResult(
            success=output.success,
            updates=updates,
            error=output.error,
            output_preview=candidate_answer[:1000],
            metadata={
                "source_agent": source_agent,
                "retry_count": retry_count,
            },
        )

    def _reviewer_node(self, state: GraphState) -> GraphNodeResult:
        blackboard = self._blackboard(state)
        candidate_answer = state.metadata.get("current_answer", "")
        source_agent = state.metadata.get("source_agent", "unknown")

        output = self.reviewer.run(
            SubAgentInput(
                blackboard=blackboard,
                instruction="Review the candidate answer.",
                metadata={
                    "candidate_answer": candidate_answer,
                    "source_agent": source_agent,
                },
            )
        )

        review_result = output.updates.get("review_result", {})
        retry_count = int(state.metadata.get("retry_count", 0))

        updates: dict[str, Any] = {
            "blackboard": blackboard,
            "review_output": output.model_dump(),
            "review_result": review_result,
        }

        if retry_count > 0:
            retry_reviews = list(
                state.metadata.get("specialist_retry_review_outputs") or []
            )
            retry_reviews.append(output.model_dump())
            updates["specialist_retry_review_outputs"] = retry_reviews

        return GraphNodeResult(
            success=output.success,
            updates=updates,
            error=output.error,
            output_preview=output.content[:1000],
            metadata={
                "passed": review_result.get("passed"),
                "confidence": review_result.get("confidence"),
                "retry_count": retry_count,
            },
        )

    def _retry_node(self, state: GraphState) -> GraphNodeResult:
        review_result = state.metadata.get("review_result") or {}
        previous_answer = state.metadata.get("current_answer", "")
        retry_count = int(state.metadata.get("retry_count", 0)) + 1

        retry_instruction = self._build_retry_instruction(
            user_request=state.user_request,
            review_result=review_result,
            previous_answer=previous_answer,
        )

        blackboard = self._blackboard(state)
        blackboard.add_note(
            author="graph_retry",
            content=f"Retrying specialist. Retry count: {retry_count}.",
            metadata={
                "review_result": review_result,
            },
        )

        return GraphNodeResult(
            success=True,
            updates={
                "blackboard": blackboard,
                "retry_count": retry_count,
                "current_instruction": retry_instruction,
            },
            output_preview=f"Prepared retry instruction. Retry count: {retry_count}.",
            metadata={
                "retry_count": retry_count,
            },
        )

    def _writer_node(self, state: GraphState) -> GraphNodeResult:
        blackboard = self._blackboard(state)
        candidate_answer = state.metadata.get("current_answer", "")
        review_result = state.metadata.get("review_result") or {}
        source_agent = state.metadata.get("source_agent", "unknown")

        output = self.writer.run(
            SubAgentInput(
                blackboard=blackboard,
                instruction="Rewrite the candidate answer using reviewer feedback.",
                metadata={
                    "candidate_answer": candidate_answer,
                    "review_result": review_result,
                    "source_agent": source_agent,
                },
            )
        )

        final_answer = output.content if output.success and output.content.strip() else candidate_answer

        return GraphNodeResult(
            success=output.success,
            updates={
                "blackboard": blackboard,
                "writer_output": output.model_dump(),
                "current_answer": final_answer,
            },
            error=output.error,
            output_preview=final_answer[:1000],
            metadata={
                "writer_triggered": True,
            },
        )

    def _final_node(self, state: GraphState) -> GraphNodeResult:
        final_answer = state.metadata.get("current_answer") or state.final_answer

        if not final_answer:
            planner_output = state.metadata.get("planner_output")
            final_answer = (
                "The graph multi-agent workflow did not produce a specialist answer.\n\n"
                f"Planner output:\n{planner_output}"
            )

        return GraphNodeResult(
            success=True,
            is_final=True,
            final_answer=final_answer,
            output_preview=final_answer[:1000],
            metadata={
                "visited_nodes": state.visited_nodes,
            },
        )

    def _route_after_planner(
        self,
        state: GraphState,
        result: GraphNodeResult,
    ) -> str | None:
        decision = state.metadata.get("planner_decision") or {}
        next_agent = decision.get("next_agent")

        if next_agent == "code":
            return "code"

        if next_agent == "paper":
            return "paper"

        if next_agent == "both":
            return "code_and_paper"

        # If no specialist is selected, do not stop directly.
        # Route to the general fallback agent so open-ended questions can still be answered.
        return "general"

    def _route_after_review(
        self,
        state: GraphState,
        result: GraphNodeResult,
    ) -> str | None:
        review_result = state.metadata.get("review_result") or {}

        if review_result.get("passed", True):
            return "final"

        source_agent = state.metadata.get("source_agent")
        retry_count = int(state.metadata.get("retry_count", 0))

        if (
            source_agent in self.retry_policy.allowed_retry_agents
            and retry_count < self.retry_policy.max_retries
        ):
            return "retry"

        if self.retry_policy.fallback_to_writer:
            return "writer"
        return "final"

    def _route_after_retry(
        self,
        state: GraphState,
        result: GraphNodeResult,
    ) -> str | None:
        source_agent = state.metadata.get("source_agent")

        if source_agent == "code":
            return "code"

        if source_agent == "paper":
            return "paper"

        return "writer"

    def _blackboard(self, state: GraphState) -> ResearchPilotBlackboard:
        blackboard = state.metadata.get("blackboard")

        if isinstance(blackboard, ResearchPilotBlackboard):
            return blackboard

        if isinstance(blackboard, dict):
            return ResearchPilotBlackboard.model_validate(blackboard)

        blackboard = ResearchPilotBlackboard(user_request=state.user_request)
        state.metadata["blackboard"] = blackboard
        return blackboard

    @staticmethod
    def _answer_from_specialist_output(
        specialist_output,
        source_agent: str,
    ) -> str:
        if not specialist_output.success:
            return (
                f"{source_agent.capitalize()}SubAgent failed.\n\n"
                f"{specialist_output.error}"
            )

        return specialist_output.content

    @staticmethod
    def _build_retry_instruction(
        user_request: str,
        review_result: dict,
        previous_answer: str,
    ) -> str:
        issues = review_result.get("issues") or []
        missing_evidence = review_result.get("missing_evidence") or []
        unsupported_claims = review_result.get("unsupported_claims") or []
        suggestions = review_result.get("suggestions") or []

        return f"""Original user request:
{user_request}

The previous answer did not pass review.

Reviewer issues:
{issues}

Missing evidence:
{missing_evidence}

Unsupported claims:
{unsupported_claims}

Reviewer suggestions:
{suggestions}

Previous answer:
{previous_answer}

Retry instruction:
Run the specialist workflow again. Try to collect stronger evidence if possible.
For code tasks, preserve exact class/function/file names and search for the relevant implementation.
For paper tasks, preserve exact research topic terms and use retrieved paper evidence.
If the evidence is still insufficient, clearly state the limitation in the final answer.
"""

    @staticmethod
    def _attach_metadata(
        state: AgentState,
        key: str,
        value,
    ) -> None:
        if hasattr(state, "metadata") and isinstance(state.metadata, dict):
            state.metadata[key] = value

    def _sanitize_graph_state(self, graph_state: GraphState) -> dict[str, Any]:
        payload = graph_state.model_dump()
        payload["metadata"] = self._sanitize_metadata(graph_state.metadata)
        return payload

    def _sanitize_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}

        for key, value in metadata.items():
            if key == "session_obj":
                continue

            if isinstance(value, ResearchPilotBlackboard):
                result[key] = value.model_dump()
            elif isinstance(value, ConversationSession):
                result[key] = value.model_dump()
            else:
                result[key] = value

        return result