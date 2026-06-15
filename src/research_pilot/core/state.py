from pydantic import BaseModel, Field
from typing import Any

from research_pilot.core.action import AgentAction
from research_pilot.core.evidence import EvidenceStore
from research_pilot.core.observation import Observation
from research_pilot.core.todo import TodoList


class AgentStep(BaseModel):
    """One step in the Agent loop."""

    step_id: int
    action: AgentAction
    observation: Observation | None = None


class AgentState(BaseModel):
    """State maintained by the Agent loop."""

    user_goal: str
    steps: list[AgentStep] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    todo_list: TodoList = Field(default_factory=TodoList)
    evidence_store: EvidenceStore = Field(default_factory=EvidenceStore)
    todo_reminder: str | None = None
    final_answer: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def add_step(self, step: AgentStep) -> None:
        self.steps.append(step)

    def add_note(self, note: str) -> None:
        self.notes.append(note)