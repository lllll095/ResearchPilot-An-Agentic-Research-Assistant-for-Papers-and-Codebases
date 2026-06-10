from datetime import datetime
from pathlib import Path

from research_pilot.core.observation import Observation
from research_pilot.core.tool import BaseTool, ToolSpec


class SaveNoteTool(BaseTool):
    name = "save_note"
    description = "Save a research note to the workspace."

    def __init__(self, note_dir: Path):
        self.note_dir = note_dir
        self.note_dir.mkdir(parents=True, exist_ok=True)

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "title": "Short title for the note. Use letters, numbers, hyphen, or underscore.",
                "content": "Markdown content of the note.",
            },
        )

    def run(self, tool_input: dict, state=None) -> Observation:
        title = tool_input.get("title", "untitled_note")
        content = tool_input.get("content", "")

        safe_title = "".join(
            ch if ch.isalnum() or ch in ("-", "_") else "_"
            for ch in title
        )

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.note_dir / f"{timestamp}_{safe_title}.md"

        path.write_text(content, encoding="utf-8")

        if state is not None:
            state.add_note(str(path))

        return Observation(
            success=True,
            content=f"Note saved to {path}",
            metadata={"path": str(path)},
        )