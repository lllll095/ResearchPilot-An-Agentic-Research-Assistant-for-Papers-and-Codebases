from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from research_pilot.core.observation import Observation


class ToolSpec(BaseModel):
    """Metadata describing a tool, including input and output schemas."""

    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] | None = None

    def validate_input(self, tool_input: dict[str, Any]) -> str | None:
        """Validate tool_input against input_schema. Returns error msg or None."""
        for field_name, field_desc in self.input_schema.items():
            if field_name not in tool_input:
                return f"Missing required input: '{field_name}' ({field_desc})"
        return None

    def validate_output_data(self, data: dict[str, Any] | None) -> str | None:
        """Validate tool output data against output_schema. Returns error msg or None."""
        if self.output_schema is None or data is None:
            return None
        for field_name, field_desc in self.output_schema.items():
            if field_name not in data:
                return f"Missing expected output: '{field_name}' ({field_desc})"
        return None


class BaseTool(ABC):
    """Base class for all tools."""

    name: str
    description: str

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={},
            output_schema=None,
        )

    @abstractmethod
    def run(self, tool_input: dict[str, Any], state: Any | None = None) -> Observation:
        """Execute the tool and return an observation."""
        raise NotImplementedError