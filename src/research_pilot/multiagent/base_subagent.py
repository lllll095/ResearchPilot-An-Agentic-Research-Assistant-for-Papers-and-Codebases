# src/research_pilot/multiagent/base_subagent.py

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from research_pilot.multiagent.blackboard import ResearchPilotBlackboard


class SubAgentInput(BaseModel):
    """Input passed to a subagent."""

    blackboard: ResearchPilotBlackboard
    instruction: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class SubAgentOutput(BaseModel):
    """Output returned by a subagent."""

    agent_name: str
    success: bool = True
    content: str = ""
    updates: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class BaseSubAgent(ABC):
    """Base interface for future multi-agent roles."""

    name: str = "base_subagent"
    description: str = "Base subagent interface."

    @abstractmethod
    def run(self, agent_input: SubAgentInput) -> SubAgentOutput:
        """Run the subagent on the shared blackboard."""

    def add_note(
        self,
        blackboard: ResearchPilotBlackboard,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Write a note to the shared blackboard."""

        blackboard.add_note(
            author=self.name,
            content=content,
            metadata=metadata or {},
        )