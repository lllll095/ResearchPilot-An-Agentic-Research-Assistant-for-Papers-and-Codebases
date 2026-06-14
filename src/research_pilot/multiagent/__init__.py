# src/research_pilot/multiagent/__init__.py

from research_pilot.multiagent.base_subagent import (
    BaseSubAgent,
    SubAgentInput,
    SubAgentOutput,
)
from research_pilot.multiagent.blackboard import (
    BlackboardNote,
    ResearchPilotBlackboard,
)

__all__ = [
    "BaseSubAgent",
    "SubAgentInput",
    "SubAgentOutput",
    "BlackboardNote",
    "ResearchPilotBlackboard",
]