# src/research_pilot/multiagent/subagents/general_subagent.py

from research_pilot.core.agent_loop import AgentLoop
from research_pilot.core.llm_client import OpenAICompatibleLLMClient
from research_pilot.multiagent.base_subagent import (
    BaseSubAgent,
    SubAgentInput,
    SubAgentOutput,
)


class GeneralSubAgent(BaseSubAgent):
    """General-purpose fallback subagent.

    This agent is used when the planner does not route the task to a
    specialized code or paper agent.

    It first tries to use the original AgentLoop, so open-ended tasks can still
    benefit from tool calling, search, paper download, or other available tools.

    If AgentLoop is unavailable or fails, it falls back to a direct LLM answer.
    """

    name = "general"
    description = "Handle general questions that are not routed to code or paper agents."

    def __init__(
        self,
        agent_loop: AgentLoop | None = None,
        llm_client: OpenAICompatibleLLMClient | None = None,
    ):
        self.agent_loop = agent_loop
        self.llm_client = llm_client

    def run(self, agent_input: SubAgentInput) -> SubAgentOutput:
        blackboard = agent_input.blackboard
        user_request = agent_input.instruction or blackboard.user_request

        if self.agent_loop is not None:
            try:
                state = self.agent_loop.run(user_request)

                blackboard.merge_agent_state(state)

                answer = state.final_answer or ""

                if answer.strip():
                    blackboard.add_note(
                        author=self.name,
                        content="Answered the request using the general AgentLoop fallback.",
                        metadata={
                            "used_agent_loop": True,
                        },
                    )

                    return SubAgentOutput(
                        agent_name=self.name,
                        success=True,
                        content=answer,
                        updates={
                            "used_agent_loop": True,
                        },
                    )

            except Exception as exc:
                blackboard.add_note(
                    author=self.name,
                    content="General AgentLoop fallback failed; trying direct LLM fallback.",
                    metadata={
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )

                if self.llm_client is None:
                    return SubAgentOutput(
                        agent_name=self.name,
                        success=False,
                        content="",
                        error=f"General AgentLoop failed and no LLM fallback is available: {type(exc).__name__}: {exc}",
                        updates={
                            "used_agent_loop": True,
                            "used_direct_llm": False,
                        },
                    )

        if self.llm_client is not None:
            try:
                answer = self._direct_llm_answer(
                    user_request=user_request,
                    blackboard_context=blackboard.compact_context(for_subagent="general"),
                )

                blackboard.add_note(
                    author=self.name,
                    content="Answered the request using direct LLM fallback.",
                    metadata={
                        "used_agent_loop": self.agent_loop is not None,
                        "used_direct_llm": True,
                    },
                )

                return SubAgentOutput(
                    agent_name=self.name,
                    success=True,
                    content=answer,
                    updates={
                        "used_agent_loop": self.agent_loop is not None,
                        "used_direct_llm": True,
                    },
                )

            except Exception as exc:
                return SubAgentOutput(
                    agent_name=self.name,
                    success=False,
                    content="",
                    error=f"Direct LLM fallback failed: {type(exc).__name__}: {exc}",
                    updates={
                        "used_direct_llm": True,
                    },
                )

        return SubAgentOutput(
            agent_name=self.name,
            success=False,
            content="",
            error="No general fallback is available. Both agent_loop and llm_client are None.",
        )

    def _direct_llm_answer(
        self,
        user_request: str,
        blackboard_context: str,
    ) -> str:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are ResearchPilot's general fallback assistant. "
                    "Answer the user's question clearly and directly. "
                    "Use the same language as the user. "
                    "If the question requires up-to-date facts or citations and no tools are available, "
                    "state that limitation honestly."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"User request:\n{user_request}\n\n"
                    f"Available blackboard context:\n{blackboard_context}\n\n"
                    "Please answer the user request."
                ),
            },
        ]

        return self.llm_client.complete(messages).strip()