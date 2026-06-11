from datetime import datetime
from pathlib import Path

from research_pilot.core.observation import Observation
from research_pilot.core.tool import BaseTool, ToolSpec


class SaveReportTool(BaseTool):
    name = "save_report"
    description = "Save the final research report to the workspace."

    def __init__(self, report_dir: Path):
        self.report_dir = report_dir
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "title": "Short report title.",
                "content": "Markdown content of the final research report.",
            },
        )

    def run(self, tool_input: dict, state=None) -> Observation:
        title = tool_input.get("title", "research_report")
        content = tool_input.get("content", "")

        if not content:
            return Observation(
                success=False,
                content="Missing input: content",
                error="MissingContent",
            )

        safe_title = "".join(
            ch if ch.isalnum() or ch in ("-", "_") else "_"
            for ch in title
        )

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.report_dir / f"{timestamp}_{safe_title}.md"

        path.write_text(content, encoding="utf-8")

        if state is not None:
            state.add_note(str(path))

        return Observation(
            success=True,
            content=f"Report saved to {path}",
            metadata={"path": str(path)},
        )