from datetime import datetime
from typing import Any

from rich.console import Console

from research_pilot.core.action import ActionType, AgentAction
from research_pilot.core.observation import Observation
from research_pilot.core.state import AgentState, AgentStep
from research_pilot.core.tool_runtime import ToolRuntime
from research_pilot.core.trace import TraceStore


class CodeWorkflowRunner:
    """Deterministic workflows for codebase understanding."""

    def __init__(
        self,
        tool_runtime: ToolRuntime,
        trace_store: TraceStore,
        console: Console | None = None,
    ):
        self.tool_runtime = tool_runtime
        self.trace_store = trace_store
        self.console = console or Console()

    def code_answer(
        self,
        question: str,
        path: str = "src/research_pilot",
        max_results: int = 20,
        max_files_to_read: int = 3,
    ) -> AgentState:
        """Answer a codebase question using code search and code read evidence."""

        run_id = self._new_run_id("code_answer")
        state = AgentState(user_goal=f"Code answer workflow: {question}")
        step_id = 1

        _, step_id = self._run_tool(
            run_id=run_id,
            step_id=step_id,
            state=state,
            tool_name="code_map",
            tool_input={
                "path": path,
                "max_files": 200,
            },
        )

        search_obs, step_id = self._run_tool(
            run_id=run_id,
            step_id=step_id,
            state=state,
            tool_name="code_search",
            tool_input={
                "query": question,
                "path": path,
                "max_results": max_results,
                "context_lines": 3,
            },
        )

        if not search_obs.success:
            return self._finalize(
                run_id=run_id,
                step_id=step_id,
                state=state,
                final_answer=(
                    "Code answer workflow failed during code_search.\n\n"
                    f"{search_obs.content}"
                ),
            )

        files_to_read = self._select_files_to_read(
            search_obs=search_obs,
            max_files=max_files_to_read,
        )

        for item in files_to_read:
            _, step_id = self._run_tool(
                run_id=run_id,
                step_id=step_id,
                state=state,
                tool_name="code_read",
                tool_input={
                    "path": item["file"],
                    "start_line": item["start_line"],
                    "max_lines": item["max_lines"],
                },
            )

        answer_obs, step_id = self._run_tool(
            run_id=run_id,
            step_id=step_id,
            state=state,
            tool_name="write_code_answer",
            tool_input={
                "question": question,
                "max_evidence_items": 15,
                "max_chars_per_item": 4500,
            },
        )

        if not answer_obs.success:
            return self._finalize(
                run_id=run_id,
                step_id=step_id,
                state=state,
                final_answer=(
                    "Code answer workflow failed during write_code_answer.\n\n"
                    f"{answer_obs.content}"
                ),
            )

        return self._finalize(
            run_id=run_id,
            step_id=step_id,
            state=state,
            final_answer=answer_obs.content,
        )

    def _select_files_to_read(
        self,
        search_obs: Observation,
        max_files: int = 3,
    ) -> list[dict[str, Any]]:
        metadata = search_obs.metadata or {}
        matches = metadata.get("matches", [])

        selected: list[dict[str, Any]] = []
        seen_files: set[str] = set()

        if not isinstance(matches, list):
            return selected

        for match in matches:
            file = match.get("file")
            line = int(match.get("line", 1) or 1)

            if not file:
                continue

            if file in seen_files:
                continue

            seen_files.add(file)

            selected.append(
                {
                    "file": file,
                    "start_line": max(1, line - 40),
                    "max_lines": 120,
                }
            )

            if len(selected) >= max_files:
                break

        return selected

    def _select_files_to_read_from_many(
        self,
        search_observations: list[Observation],
        max_files: int = 5,
    ) -> list[dict[str, Any]]:
        """Select files to read from multiple search observations."""

        selected: list[dict[str, Any]] = []
        seen_files: set[str] = set()

        for obs in search_observations:
            candidates = self._select_files_to_read(
                search_obs=obs,
                max_files=max_files,
            )

            for item in candidates:
                file = item.get("file")
                if not file:
                    continue

                normalized = file.lower().replace("\\", "/")
                if normalized in seen_files:
                    continue

                seen_files.add(normalized)
                selected.append(item)

                if len(selected) >= max_files:
                    return selected

        return selected

    def _run_tool(
        self,
        run_id: str,
        step_id: int,
        state: AgentState,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> tuple[Observation, int]:
        action = AgentAction(
            action_type=ActionType.TOOL_CALL,
            tool_name=tool_name,
            tool_input=tool_input,
            thought_summary=f"Workflow calls {tool_name}.",
        )

        self.console.print(f"[yellow]Step {step_id}: tool_call -> {tool_name}[/yellow]")

        observation = self.tool_runtime.execute(action, state=state)

        step = AgentStep(
            step_id=step_id,
            action=action,
            observation=observation,
        )

        state.add_step(step)
        self.trace_store.save_step(run_id, step)

        if observation.success:
            preview = observation.content[:1500]
            self.console.print(f"[green]Observation:[/green] {preview}")
            if len(observation.content) > 1500:
                self.console.print("[dim]Observation truncated in console.[/dim]")
        else:
            self.console.print(f"[red]Tool error:[/red] {observation.error}")
            self.console.print(f"[red]Details:[/red] {observation.content}")

        return observation, step_id + 1

    def _finalize(
        self,
        run_id: str,
        step_id: int,
        state: AgentState,
        final_answer: str,
    ) -> AgentState:
        action = AgentAction(
            action_type=ActionType.FINAL_ANSWER,
            final_answer=final_answer,
            thought_summary="Code workflow completed.",
        )

        step = AgentStep(
            step_id=step_id,
            action=action,
            observation=None,
        )

        state.final_answer = final_answer
        state.add_step(step)

        self.trace_store.save_step(run_id, step)
        final_path = self.trace_store.save_final_state(run_id, state)

        self.console.print(f"[dim]Trace saved to: {final_path}[/dim]")

        return state

    def _extra_search_queries(self, question: str) -> list[str]:
        """Add targeted searches for known codebase question patterns."""

        q = question.lower()

        queries: list[str] = []

        if "agentloop" in q or "agent loop" in q:
            queries.extend(
                [
                    "class AgentLoop",
                    "def run AgentLoop",
                    "AgentLoop ToolRuntime TraceStore AgentState",
                    "agent_loop.py AgentLoop",
                ]
            )

        if "toolruntime" in q or "tool runtime" in q:
            queries.extend(
                [
                    "class ToolRuntime",
                    "def execute ToolRuntime",
                    "ToolRuntime execute tool_name tool_input",
                ]
            )

        if "codeworkflowrunner" in q or "code workflow" in q:
            queries.extend(
                [
                    "class CodeWorkflowRunner",
                    "def code_answer CodeWorkflowRunner",
                    "code_search code_read write_code_answer",
                ]
            )

        if "ask" in q and ("route" in q or "routing" in q or "code-answer" in q):
            queries.extend(
                [
                    "IntentType CODE_ANSWER",
                    "def ask routed.intent_type CODE_ANSWER",
                    "build_code_workflow_runner code_answer",
                ]
            )

        return list(dict.fromkeys(queries))

    @staticmethod
    def _new_run_id(prefix: str) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{prefix}_{timestamp}"