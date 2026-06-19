from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EvidenceType(str, Enum):
    WEB_SEARCH = "web_search"
    NOTE = "note"
    REPORT = "report"
    FILE = "file"
    CODE = "code"
    PAPER = "paper"


class EvidenceItem(BaseModel):
    """A piece of evidence collected during an Agent run."""

    evidence_type: EvidenceType
    source: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceStore(BaseModel):
    """Store evidence collected during an Agent run."""

    items: list[EvidenceItem] = Field(default_factory=list)

    def add(self, item: EvidenceItem) -> None:
        self.items.append(item)

    def is_empty(self) -> bool:
        return len(self.items) == 0

    def render(self, max_items: int = 8, max_chars_per_item: int = 600) -> str:
        if not self.items:
            return "No evidence collected yet."

        lines = []

        for idx, item in enumerate(self.items[-max_items:], start=1):
            content = item.content

            if len(content) > max_chars_per_item:
                content = content[:max_chars_per_item] + "\n[Evidence truncated]"

            lines.append(f"Evidence {idx}:")
            lines.append(f"- type: {item.evidence_type}")
            lines.append(f"- source: {item.source}")

            # Show structured data keys if present
            data = item.metadata.get("data")
            if isinstance(data, dict) and data:
                data_keys = ", ".join(data.keys())
                lines.append(f"- structured_data: {{{data_keys}}}")

            lines.append(f"- content:")
            lines.append(content)
            lines.append("")

        return "\n".join(lines)