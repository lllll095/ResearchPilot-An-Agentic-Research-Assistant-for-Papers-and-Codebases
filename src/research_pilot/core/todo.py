from enum import Enum

from pydantic import BaseModel, Field


class TodoStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TodoItem(BaseModel):
    """One todo item maintained by the Agent."""

    id: str
    content: str
    status: TodoStatus = TodoStatus.PENDING
    notes: str | None = None


class TodoList(BaseModel):
    """A list of todo items for the current Agent run."""

    items: list[TodoItem] = Field(default_factory=list)

    def is_empty(self) -> bool:
        return len(self.items) == 0

    def all_done(self) -> bool:
        if not self.items:
            return False

        return all(
            item.status in {TodoStatus.COMPLETED, TodoStatus.CANCELLED}
            for item in self.items
        )

    def render(self) -> str:
        if not self.items:
            return "No todo items yet."

        lines = []
        for item in self.items:
            marker = {
                TodoStatus.PENDING: "[ ]",
                TodoStatus.IN_PROGRESS: "[~]",
                TodoStatus.COMPLETED: "[x]",
                TodoStatus.CANCELLED: "[-]",
            }[item.status]

            line = f"{marker} {item.id}. {item.content} ({item.status})"

            if item.notes:
                line += f" - {item.notes}"

            lines.append(line)

        return "\n".join(lines)