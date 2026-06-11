from datetime import datetime
from typing import Any

from rich.console import Console

from research_pilot.core.action import ActionType, AgentAction
from research_pilot.core.observation import Observation
from research_pilot.core.state import AgentState, AgentStep
from research_pilot.core.tool_runtime import ToolRuntime
from research_pilot.core.trace import TraceStore


class PaperWorkflowRunner:
    """Deterministic workflows for paper research tasks.

    These workflows reduce random tool selection by fixing the high-value
    orchestration path while still using LLM-powered tools for generation.
    """

    def __init__(
        self,
        tool_runtime: ToolRuntime,
        trace_store: TraceStore,
        console: Console | None = None,
    ):
        self.tool_runtime = tool_runtime
        self.trace_store = trace_store
        self.console = console or Console()

    def paper_answer(
        self,
        question: str,
        save_report: bool = False,
        report_title: str | None = None,
        paper_k: int | None = None,
        chunk_k: int | None = None,
    ) -> AgentState:
        """Answer a question using already indexed papers."""

        run_id = self._new_run_id("paper_answer")
        state = AgentState(user_goal=f"Paper answer workflow: {question}")
        step_id = 1

        search_input: dict[str, Any] = {"query": question}
        if paper_k is not None:
            search_input["paper_k"] = paper_k
        if chunk_k is not None:
            search_input["chunk_k"] = chunk_k

        search_obs, step_id = self._run_tool(
            run_id=run_id,
            step_id=step_id,
            state=state,
            tool_name="engineered_rag_search",
            tool_input=search_input,
        )

        if not search_obs.success:
            return self._finalize(
                run_id=run_id,
                step_id=step_id,
                state=state,
                final_answer=(
                    "Paper answer workflow failed during engineered_rag_search.\n\n"
                    f"{search_obs.content}"
                ),
            )

        answer_obs, step_id = self._run_tool(
            run_id=run_id,
            step_id=step_id,
            state=state,
            tool_name="write_evidence_answer",
            tool_input={
                "question": question,
                "max_evidence_items": 8,
                "max_chars_per_item": 4500,
            },
        )

        if not answer_obs.success:
            return self._finalize(
                run_id=run_id,
                step_id=step_id,
                state=state,
                final_answer=(
                    "Paper answer workflow failed during write_evidence_answer.\n\n"
                    f"{answer_obs.content}"
                ),
            )

        final_answer = answer_obs.content

        if save_report:
            title = report_title or self._safe_title(question)
            report_obs, step_id = self._run_tool(
                run_id=run_id,
                step_id=step_id,
                state=state,
                tool_name="save_report",
                tool_input={
                    "title": title,
                    "content": final_answer,
                },
            )

            if report_obs.success:
                final_answer += f"\n\n---\n\nReport saved: {report_obs.metadata.get('path')}"

        return self._finalize(
            run_id=run_id,
            step_id=step_id,
            state=state,
            final_answer=final_answer,
        )

    def paper_collect(
        self,
        topic: str,
        max_papers: int = 3,
        rebuild_index: bool = True,
    ) -> AgentState:
        """Search and download papers for a topic, then optionally rebuild index."""

        run_id = self._new_run_id("paper_collect")
        state = AgentState(user_goal=f"Paper collection workflow: {topic}")
        step_id = 1

        search_obs, step_id = self._run_tool(
            run_id=run_id,
            step_id=step_id,
            state=state,
            tool_name="paper_search",
            tool_input={
                "query": topic,
                "max_results": max(max_papers * 3, 5),
            },
        )

        download_obs, step_id = self._run_tool(
            run_id=run_id,
            step_id=step_id,
            state=state,
            tool_name="paper_download",
            tool_input={
                "query": topic,
                "max_papers": max_papers,
            },
        )

        if not download_obs.success:
            return self._finalize(
                run_id=run_id,
                step_id=step_id,
                state=state,
                final_answer=(
                    "Paper collection workflow failed during paper_download.\n\n"
                    f"{download_obs.content}"
                ),
            )

        index_obs = None
        if rebuild_index:
            index_obs, step_id = self._run_tool(
                run_id=run_id,
                step_id=step_id,
                state=state,
                tool_name="engineered_rag_index",
                tool_input={
                    "sync_downloaded_papers": True,
                },
            )

        note_content = self._build_collection_summary(
            topic=topic,
            search_obs=search_obs,
            download_obs=download_obs,
            index_obs=index_obs,
        )

        note_obs, step_id = self._run_tool(
            run_id=run_id,
            step_id=step_id,
            state=state,
            tool_name="save_note",
            tool_input={
                "title": f"paper_collection_{self._safe_title(topic)}",
                "content": note_content,
            },
        )

        final_answer = note_content
        if note_obs.success:
            final_answer += f"\n\nCollection note saved: {note_obs.metadata.get('path')}"

        return self._finalize(
            run_id=run_id,
            step_id=step_id,
            state=state,
            final_answer=final_answer,
        )

    def paper_research(
        self,
        question: str,
        max_papers: int = 3,
        min_sources: int = 3,
        force_download: bool = False,
        save_report: bool = True,
        report_title: str | None = None,
    ) -> AgentState:
        """Local-first full paper research workflow.

        It first searches indexed papers. If evidence seems insufficient,
        it downloads more papers, rebuilds the index, searches again, then
        writes a citation-aware answer and optionally saves a report.
        """

        run_id = self._new_run_id("paper_research")
        state = AgentState(user_goal=f"Paper research workflow: {question}")
        step_id = 1

        search_obs: Observation | None = None

        if not force_download:
            search_obs, step_id = self._run_tool(
                run_id=run_id,
                step_id=step_id,
                state=state,
                tool_name="engineered_rag_search",
                tool_input={
                    "query": question,
                },
            )

        enough = (
            search_obs is not None
            and search_obs.success
            and self._evidence_is_sufficient(search_obs, min_sources=min_sources)
        )

        if force_download or not enough:
            self.console.print(
                "[yellow]Local evidence is insufficient or download was forced. "
                "Collecting more papers...[/yellow]"
            )

            download_obs, step_id = self._run_tool(
                run_id=run_id,
                step_id=step_id,
                state=state,
                tool_name="paper_download",
                tool_input={
                    "query": question,
                    "max_papers": max_papers,
                },
            )

            if not download_obs.success:
                return self._finalize(
                    run_id=run_id,
                    step_id=step_id,
                    state=state,
                    final_answer=(
                        "Paper research workflow failed during paper_download.\n\n"
                        f"{download_obs.content}"
                    ),
                )

            index_obs, step_id = self._run_tool(
                run_id=run_id,
                step_id=step_id,
                state=state,
                tool_name="engineered_rag_index",
                tool_input={
                    "sync_downloaded_papers": True,
                },
            )

            if not index_obs.success:
                return self._finalize(
                    run_id=run_id,
                    step_id=step_id,
                    state=state,
                    final_answer=(
                        "Paper research workflow failed during engineered_rag_index.\n\n"
                        f"{index_obs.content}"
                    ),
                )

            search_obs, step_id = self._run_tool(
                run_id=run_id,
                step_id=step_id,
                state=state,
                tool_name="engineered_rag_search",
                tool_input={
                    "query": question,
                },
            )

            if not search_obs.success:
                return self._finalize(
                    run_id=run_id,
                    step_id=step_id,
                    state=state,
                    final_answer=(
                        "Paper research workflow failed during engineered_rag_search "
                        "after downloading papers.\n\n"
                        f"{search_obs.content}"
                    ),
                )

        answer_obs, step_id = self._run_tool(
            run_id=run_id,
            step_id=step_id,
            state=state,
            tool_name="write_evidence_answer",
            tool_input={
                "question": question,
                "max_evidence_items": 10,
                "max_chars_per_item": 4500,
            },
        )

        if not answer_obs.success:
            return self._finalize(
                run_id=run_id,
                step_id=step_id,
                state=state,
                final_answer=(
                    "Paper research workflow failed during write_evidence_answer.\n\n"
                    f"{answer_obs.content}"
                ),
            )

        final_answer = answer_obs.content

        if save_report:
            title = report_title or self._safe_title(question)
            report_obs, step_id = self._run_tool(
                run_id=run_id,
                step_id=step_id,
                state=state,
                tool_name="save_report",
                tool_input={
                    "title": title,
                    "content": final_answer,
                },
            )

            if report_obs.success:
                final_answer += f"\n\n---\n\nReport saved: {report_obs.metadata.get('path')}"

        return self._finalize(
            run_id=run_id,
            step_id=step_id,
            state=state,
            final_answer=final_answer,
        )

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
            self.console.print(f"[green]Observation:[/green] {observation.content}")
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
            thought_summary="Workflow completed.",
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

    @staticmethod
    def _new_run_id(prefix: str) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{prefix}_{timestamp}"

    @staticmethod
    def _safe_title(text: str, max_len: int = 80) -> str:
        safe = "".join(
            ch if ch.isalnum() or ch in ("-", "_") else "_"
            for ch in text.strip()
        )
        safe = "_".join(part for part in safe.split("_") if part)
        return safe[:max_len] or "paper_report"

    @staticmethod
    def _evidence_is_sufficient(
        observation: Observation,
        min_sources: int = 3,
        min_chars: int = 800,
    ) -> bool:
        if not observation.success:
            return False

        metadata = observation.metadata or {}

        num_docs = int(metadata.get("num_docs", 0) or 0)
        evidence_blocks = metadata.get("evidence_blocks", [])

        if isinstance(evidence_blocks, list) and len(evidence_blocks) >= min_sources:
            return True

        if num_docs >= min_sources and len(observation.content or "") >= min_chars:
            return True

        return False

    @staticmethod
    def _build_collection_summary(
        topic: str,
        search_obs: Observation,
        download_obs: Observation,
        index_obs: Observation | None,
    ) -> str:
        lines = [
            f"# Paper Collection Summary",
            "",
            f"Topic: {topic}",
            "",
            "## Paper Search",
            "",
            search_obs.content if search_obs.success else f"Search failed: {search_obs.content}",
            "",
            "## Paper Download",
            "",
            download_obs.content if download_obs.success else f"Download failed: {download_obs.content}",
            "",
        ]

        if index_obs is not None:
            lines.extend(
                [
                    "## EngineeredRAG Index",
                    "",
                    index_obs.content if index_obs.success else f"Index failed: {index_obs.content}",
                    "",
                ]
            )

        return "\n".join(lines)