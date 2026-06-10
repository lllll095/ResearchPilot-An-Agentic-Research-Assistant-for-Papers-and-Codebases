from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from research_pilot.core.observation import Observation


class ToolSpec(BaseModel):
    """Metadata describing a tool."""

    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)


class BaseTool(ABC):
    """Base class for all tools."""

    name: str
    description: str

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={},
        )

    @abstractmethod
    def run(self, tool_input: dict[str, Any], state: Any | None = None) -> Observation:
        """Execute the tool and return an observation."""
        raise NotImplementedError