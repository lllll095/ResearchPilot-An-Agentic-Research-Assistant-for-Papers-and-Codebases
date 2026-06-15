# src/research_pilot/conversation/turn_memory.py

from typing import Any

from pydantic import BaseModel, Field

from research_pilot.core.state import AgentState


class TurnMemory(BaseModel):
    """Compact structured memory extracted from one agent/workflow turn."""

    user_input: str
    final_answer_preview: str = ""
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    code_files: list[str] = Field(default_factory=list)
    code_search_queries: list[str] = Field(default_factory=list)
    evidence_sources: list[str] = Field(default_factory=list)
    report_paths: list[str] = Field(default_factory=list)


class TurnMemoryExtractor:
    """Extract compact memory from an AgentState after one chat turn."""

    def extract(
        self,
        user_input: str,
        state: AgentState,
        max_answer_chars: int = 800,
    ) -> TurnMemory:
        final_answer = state.final_answer or ""

        memory = TurnMemory(
            user_input=user_input,
            final_answer_preview=final_answer[:max_answer_chars],
        )

        self._extract_steps(state, memory)
        self._extract_evidence_sources(state, memory)
        self._extract_state_metadata(state, memory)

        memory.code_files = self._dedupe(memory.code_files)
        memory.code_search_queries = self._dedupe(memory.code_search_queries)
        memory.evidence_sources = self._dedupe(memory.evidence_sources)
        memory.report_paths = self._dedupe(memory.report_paths)

        return memory

    def _extract_steps(self, state: AgentState, memory: TurnMemory) -> None:
        for step in state.steps:
            action = step.action
            observation = step.observation

            tool_name = action.tool_name
            tool_input = action.tool_input or {}

            if not tool_name:
                continue

            memory.tool_calls.append(
                {
                    "tool_name": tool_name,
                    "tool_input": tool_input,
                    "success": observation.success if observation is not None else None,
                    "error": observation.error if observation is not None else None,
                }
            )

            if tool_name == "code_search":
                query = tool_input.get("query")
                if query:
                    memory.code_search_queries.append(str(query))

            if tool_name == "code_read":
                path = tool_input.get("path")
                if path:
                    memory.code_files.append(str(path))

            if observation is not None and observation.metadata:
                self._extract_observation_metadata(
                    tool_name=tool_name,
                    metadata=observation.metadata,
                    memory=memory,
                )

    def _extract_observation_metadata(
        self,
        tool_name: str,
        metadata: dict[str, Any],
        memory: TurnMemory,
    ) -> None:
        file = metadata.get("file")
        if file:
            memory.code_files.append(str(file))

        path = metadata.get("path")
        if path and tool_name in {"code_read", "read_file"}:
            memory.code_files.append(str(path))

        report_path = metadata.get("report_path") or metadata.get("saved_path")
        if report_path:
            memory.report_paths.append(str(report_path))

        matches = metadata.get("matches")
        if isinstance(matches, list):
            for match in matches[:10]:
                if not isinstance(match, dict):
                    continue

                match_file = match.get("file")
                if match_file:
                    memory.code_files.append(str(match_file))

    def _extract_evidence_sources(self, state: AgentState, memory: TurnMemory) -> None:
        evidence_store = getattr(state, "evidence_store", None)

        if evidence_store is None:
            return

        items = getattr(evidence_store, "items", [])

        for item in items:
            source = getattr(item, "source", None)
            if source:
                memory.evidence_sources.append(str(source))

    def _extract_state_metadata(self, state: AgentState, memory: TurnMemory) -> None:
        """Extract memory from AgentState.metadata.

        Graph-based multi-agent workflows may not populate AgentState.steps.
        Instead, they store blackboard and graph_state in metadata.
        """

        metadata = getattr(state, "metadata", None)

        if not isinstance(metadata, dict):
            return

        blackboard = metadata.get("blackboard")

        if isinstance(blackboard, dict):
            self._extract_blackboard_metadata(blackboard, memory)

        graph_state = metadata.get("graph_state")

        if isinstance(graph_state, dict):
            graph_metadata = graph_state.get("metadata") or {}

            if isinstance(graph_metadata, dict):
                nested_blackboard = graph_metadata.get("blackboard")
                if isinstance(nested_blackboard, dict):
                    self._extract_blackboard_metadata(nested_blackboard, memory)

            visited_nodes = graph_state.get("visited_nodes") or []
            if visited_nodes:
                memory.tool_calls.append(
                    {
                        "tool_name": "graph_workflow",
                        "tool_input": {
                            "visited_nodes": visited_nodes,
                        },
                        "success": True,
                        "error": None,
                    }
                )

    def _extract_blackboard_metadata(
        self,
        blackboard: dict,
        memory: TurnMemory,
    ) -> None:
        """Extract useful fields from serialized ResearchPilotBlackboard."""

        code_files = blackboard.get("code_files") or []
        code_search_queries = blackboard.get("code_search_queries") or []
        evidence_sources = blackboard.get("evidence_sources") or []
        report_paths = blackboard.get("report_paths") or []

        memory.code_files.extend(str(item) for item in code_files)
        memory.code_search_queries.extend(str(item) for item in code_search_queries)
        memory.evidence_sources.extend(str(item) for item in evidence_sources)
        memory.report_paths.extend(str(item) for item in report_paths)

    @staticmethod
    def _dedupe(items: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []

        for item in items:
            normalized = item.strip()
            if not normalized:
                continue

            key = normalized.lower().replace("\\", "/")
            if key in seen:
                continue

            seen.add(key)
            result.append(normalized)

        return result