from typing import Any

from pydantic import BaseModel, Field


class Observation(BaseModel):
    """Result returned by a tool execution.

    Fields:
        success: Whether the tool executed successfully.
        content: Human-readable result text. Always populated.
        data: Structured result data. Tools should populate this with
              parsable fields (e.g., lists of file matches, evidence chunks).
              Consumers can use data directly instead of parsing content.
        metadata: Execution metadata (e.g., timing, source tracking).
        error: Error message if success is False.
    """

    success: bool
    content: str
    data: dict[str, Any] | None = Field(default=None)
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
