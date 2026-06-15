# src/research_pilot/multiagent/trace_report.py

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from research_pilot.config import settings
from research_pilot.core.state import AgentState


class MultiAgentTraceReportWriter:
    """Save a human-readable markdown report for one multi-agent run.

    This writer supports both:
    - legacy multi-agent runner
    - graph-based multi-agent runner

    When graph metadata is available, the report includes node path,
    step records, node output previews, retry loops, and final routing.
    """

    def __init__(self, output_dir: Path | None = None):
        self.output_dir = output_dir or (Path(settings.workspace) / "multiagent_reports")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        state: AgentState,
        user_request: str,
        session_id: str | None = None,
    ) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_session = self._safe_name(session_id or "single")
        path = self.output_dir / f"multiagent_trace_{safe_session}_{timestamp}.md"

        markdown = self.render(
            state=state,
            user_request=user_request,
            session_id=session_id,
        )

        path.write_text(markdown, encoding="utf-8")
        return path

    def render(
        self,
        state: AgentState,
        user_request: str,
        session_id: str | None = None,
    ) -> str:
        metadata = self._metadata(state)

        planner_output = metadata.get("planner_output") or {}
        review_output = metadata.get("review_output") or {}
        writer_output = metadata.get("writer_output")
        retry_outputs = metadata.get("specialist_retry_outputs") or []
        retry_review_outputs = metadata.get("specialist_retry_review_outputs") or []
        blackboard = metadata.get("blackboard") or {}
        graph_state = metadata.get("graph_state") or {}

        planner_decision = self._planner_decision(planner_output)
        review_result = self._review_result(review_output)

        runner_type = "graph-multi-agent" if graph_state else "legacy-multi-agent"

        lines: list[str] = []

        lines.extend(
            [
                "# Multi-agent Trace Report",
                "",
                f"- Generated at: `{datetime.now().isoformat(timespec='seconds')}`",
                f"- Session: `{session_id or '(none)'}`",
                f"- Runner type: `{runner_type}`",
                "",
                "## User Request",
                "",
                "```text",
                user_request,
                "```",
                "",
                "## Final Answer",
                "",
                state.final_answer or "(empty)",
                "",
                "---",
                "",
            ]
        )

        lines.extend(self._graph_execution_section(graph_state))

        lines.extend(
            [
                "## Planner Decision",
                "",
                f"- Task type: `{planner_decision.get('task_type')}`",
                f"- Next agent: `{planner_decision.get('next_agent')}`",
                f"- Reason: {planner_decision.get('reason') or '(empty)'}",
                f"- Rewritten request: {planner_decision.get('rewritten_request') or '(empty)'}",
                "",
                "### Raw Planner Output",
                "",
                "```json",
                self._json(planner_output),
                "```",
                "",
                "---",
                "",
            ]
        )

        lines.extend(self._specialist_section(metadata))

        lines.extend(
            [
                "## Reviewer Result",
                "",
                f"- Passed: `{review_result.get('passed')}`",
                f"- Confidence: `{review_result.get('confidence')}`",
                "",
            ]
        )

        issues = review_result.get("issues") or []
        missing_evidence = review_result.get("missing_evidence") or []
        unsupported_claims = review_result.get("unsupported_claims") or []
        suggestions = review_result.get("suggestions") or []

        lines.extend(self._list_section("Issues", issues))
        lines.extend(self._list_section("Missing Evidence", missing_evidence))
        lines.extend(self._list_section("Unsupported Claims", unsupported_claims))
        lines.extend(self._list_section("Suggestions", suggestions))

        lines.extend(
            [
                "### Raw Reviewer Output",
                "",
                "```json",
                self._json(review_output),
                "```",
                "",
                "---",
                "",
            ]
        )

        lines.extend(
            [
                "## Retry / Writer",
                "",
                f"- Specialist retry count: `{len(retry_outputs)}`",
                f"- Retry review count: `{len(retry_review_outputs)}`",
                f"- Writer triggered: `{writer_output is not None}`",
                "",
            ]
        )

        if retry_outputs:
            lines.extend(
                [
                    "### Specialist Retry Outputs",
                    "",
                    "```json",
                    self._json(retry_outputs, max_chars=8000),
                    "```",
                    "",
                ]
            )

        if retry_review_outputs:
            lines.extend(
                [
                    "### Specialist Retry Review Outputs",
                    "",
                    "```json",
                    self._json(retry_review_outputs, max_chars=8000),
                    "```",
                    "",
                ]
            )

        if writer_output is not None:
            lines.extend(
                [
                    "### Writer Output",
                    "",
                    "```json",
                    self._json(writer_output, max_chars=8000),
                    "```",
                    "",
                ]
            )

        lines.extend(
            [
                "---",
                "",
                "## Blackboard Summary",
                "",
            ]
        )

        lines.extend(self._blackboard_summary(blackboard))

        lines.extend(
            [
                "",
                "### Raw Blackboard Preview",
                "",
                "```json",
                self._json(blackboard, max_chars=10000),
                "```",
                "",
                "---",
                "",
                "## Full Metadata Preview",
                "",
                "```json",
                self._json(metadata, max_chars=16000),
                "```",
                "",
            ]
        )

        return "\n".join(lines)

    @staticmethod
    def _metadata(state: AgentState) -> dict[str, Any]:
        metadata = getattr(state, "metadata", None)
        return metadata if isinstance(metadata, dict) else {}

    @staticmethod
    def _planner_decision(planner_output: dict[str, Any]) -> dict[str, Any]:
        updates = planner_output.get("updates") or {}
        decision = updates.get("planner_decision") or {}
        return decision if isinstance(decision, dict) else {}

    @staticmethod
    def _review_result(review_output: dict[str, Any]) -> dict[str, Any]:
        updates = review_output.get("updates") or {}
        result = updates.get("review_result") or {}
        return result if isinstance(result, dict) else {}

    def _graph_execution_section(self, graph_state: dict[str, Any]) -> list[str]:
        lines: list[str] = [
            "## Graph Execution",
            "",
        ]

        if not isinstance(graph_state, dict) or not graph_state:
            lines.extend(
                [
                    "- Graph state: `(not available; probably legacy runner)`",
                    "",
                    "---",
                    "",
                ]
            )
            return lines

        visited_nodes = graph_state.get("visited_nodes") or []
        step_records = graph_state.get("step_records") or []
        errors = graph_state.get("errors") or []

        lines.extend(
            [
                "### Summary",
                "",
                f"- Current node: `{graph_state.get('current_node')}`",
                f"- Is final: `{graph_state.get('is_final')}`",
                f"- Step count: `{graph_state.get('step_count')}`",
                f"- Max steps: `{graph_state.get('max_steps')}`",
                f"- Error count: `{len(errors)}`",
                "",
                "### Visited Path",
                "",
                "```text",
                self._format_path(visited_nodes),
                "```",
                "",
            ]
        )

        if errors:
            lines.extend(self._list_section("Graph Errors", errors))

        lines.extend(
            [
                "### Step Records",
                "",
            ]
        )

        lines.extend(self._step_records_table(step_records))

        lines.extend(
            [
                "",
                "### Step Details",
                "",
            ]
        )

        lines.extend(self._step_records_details(step_records))

        lines.extend(
            [
                "---",
                "",
            ]
        )

        return lines

    @staticmethod
    def _format_path(visited_nodes: list[Any]) -> str:
        if not visited_nodes:
            return "(empty)"

        return " -> ".join(str(node) for node in visited_nodes)

    def _step_records_table(self, step_records: list[Any]) -> list[str]:
        if not step_records:
            return ["(empty)", ""]

        lines = [
            "| # | Node | Success | Next | Final | Error | Preview |",
            "|---:|---|---|---|---|---|---|",
        ]

        for item in step_records:
            if not isinstance(item, dict):
                continue

            step_id = item.get("step_id")
            node_name = item.get("node_name")
            success = item.get("success")
            next_node = item.get("next_node")
            is_final = item.get("is_final")
            error = self._one_line(item.get("error") or "")
            preview = self._one_line(item.get("output_preview") or "", max_chars=140)

            lines.append(
                f"| {step_id} | `{node_name}` | `{success}` | `{next_node}` | "
                f"`{is_final}` | {error or '-'} | {preview or '-'} |"
            )

        lines.append("")
        return lines

    def _step_records_details(self, step_records: list[Any]) -> list[str]:
        if not step_records:
            return ["(empty)", ""]

        lines: list[str] = []

        for item in step_records:
            if not isinstance(item, dict):
                continue

            step_id = item.get("step_id")
            node_name = item.get("node_name")
            output_preview = item.get("output_preview") or ""
            metadata = item.get("metadata") or {}

            lines.extend(
                [
                    f"#### Step {step_id}: `{node_name}`",
                    "",
                    f"- Success: `{item.get('success')}`",
                    f"- Next node: `{item.get('next_node')}`",
                    f"- Is final: `{item.get('is_final')}`",
                    f"- Error: `{item.get('error')}`",
                    "",
                    "Output preview:",
                    "",
                    "```text",
                    str(output_preview)[:1500],
                    "```",
                    "",
                    "Metadata:",
                    "",
                    "```json",
                    self._json(metadata, max_chars=3000),
                    "```",
                    "",
                ]
            )

        return lines

    def _specialist_section(self, metadata: dict[str, Any]) -> list[str]:
        initial_output = metadata.get("initial_specialist_output")
        source_agent = metadata.get("source_agent")

        lines = [
            "## Specialist Output",
            "",
            f"- Source agent: `{source_agent}`",
            "",
        ]

        if initial_output is None:
            lines.extend(
                [
                    "- Initial specialist output: `(empty)`",
                    "",
                    "---",
                    "",
                ]
            )
            return lines

        if isinstance(initial_output, dict):
            lines.extend(
                [
                    f"- Agent name: `{initial_output.get('agent_name')}`",
                    f"- Success: `{initial_output.get('success')}`",
                    f"- Error: `{initial_output.get('error')}`",
                    "",
                    "### Specialist Answer Preview",
                    "",
                    "```markdown",
                    str(initial_output.get("content") or "")[:2000],
                    "```",
                    "",
                    "### Raw Specialist Output",
                    "",
                    "```json",
                    self._json(initial_output, max_chars=8000),
                    "```",
                    "",
                    "---",
                    "",
                ]
            )
        else:
            lines.extend(
                [
                    "```text",
                    str(initial_output)[:4000],
                    "```",
                    "",
                    "---",
                    "",
                ]
            )

        return lines

    @staticmethod
    def _list_section(title: str, items: list[Any]) -> list[str]:
        lines = [f"### {title}", ""]

        if not items:
            lines.extend(["- (none)", ""])
            return lines

        for item in items:
            lines.append(f"- {item}")

        lines.append("")
        return lines

    @staticmethod
    def _blackboard_summary(blackboard: dict[str, Any]) -> list[str]:
        lines: list[str] = []

        if not isinstance(blackboard, dict) or not blackboard:
            return ["(empty)"]

        lines.extend(
            [
                f"- Session id: `{blackboard.get('session_id')}`",
                f"- User request: `{blackboard.get('user_request')}`",
                "",
            ]
        )

        code_files = blackboard.get("code_files") or []
        code_queries = blackboard.get("code_search_queries") or []
        evidence_sources = blackboard.get("evidence_sources") or []
        report_paths = blackboard.get("report_paths") or []
        notes = blackboard.get("notes") or []

        lines.extend(MultiAgentTraceReportWriter._list_section("Code Files", code_files[:30]))
        lines.extend(MultiAgentTraceReportWriter._list_section("Code Search Queries", code_queries[:30]))
        lines.extend(MultiAgentTraceReportWriter._list_section("Evidence Sources", evidence_sources[:40]))
        lines.extend(MultiAgentTraceReportWriter._list_section("Report Paths", report_paths[:30]))

        if notes:
            note_lines = []

            for note in notes[-15:]:
                if isinstance(note, dict):
                    author = note.get("author", "unknown")
                    content = note.get("content", "")
                    note_lines.append(f"{author}: {content}")
                else:
                    note_lines.append(str(note))

            lines.extend(MultiAgentTraceReportWriter._list_section("Blackboard Notes", note_lines))
        else:
            lines.extend(MultiAgentTraceReportWriter._list_section("Blackboard Notes", []))

        return lines

    @staticmethod
    def _json(payload: Any, max_chars: int = 5000) -> str:
        text = json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
            default=str,
        )

        if len(text) > max_chars:
            return text[:max_chars] + "\n... truncated ..."

        return text

    @staticmethod
    def _safe_name(value: str) -> str:
        safe = []

        for char in value:
            if char.isalnum() or char in {"-", "_", "."}:
                safe.append(char)
            else:
                safe.append("_")

        result = "".join(safe).strip("_")
        return result or "session"

    @staticmethod
    def _one_line(value: Any, max_chars: int = 120) -> str:
        text = str(value)
        text = text.replace("\n", " ").replace("\r", " ")
        text = text.replace("|", "\\|")
        text = " ".join(text.split())

        if len(text) > max_chars:
            return text[:max_chars] + "..."

        return text