# src/research_pilot/multiagent/blackboard.py

from typing import Any

from pydantic import BaseModel, Field

from research_pilot.conversation.session import ConversationSession
from research_pilot.core.evidence import EvidenceItem
from research_pilot.core.state import AgentState


class BlackboardNote(BaseModel):
    """A compact note written by a subagent to the shared blackboard."""

    author: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResearchPilotBlackboard(BaseModel):
    """Shared workspace for future multi-agent collaboration.

    The blackboard is not a replacement for AgentState or ConversationSession.
    Instead, it provides a shared, compact, cross-agent workspace.

    AgentState:
        one execution run

    ConversationSession:
        multi-turn chat history

    ResearchPilotBlackboard:
        shared task context for multiple subagents
    """

    user_request: str
    session_id: str | None = None

    session_summary: str = ""
    recent_messages: list[dict[str, Any]] = Field(default_factory=list)
    recent_turn_memories: list[dict[str, Any]] = Field(default_factory=list)

    code_files: list[str] = Field(default_factory=list)
    code_search_queries: list[str] = Field(default_factory=list)

    evidence_sources: list[str] = Field(default_factory=list)
    evidence_items: list[dict[str, Any]] = Field(default_factory=list)

    report_paths: list[str] = Field(default_factory=list)

    notes: list[BlackboardNote] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_session(
        cls,
        user_request: str,
        session: ConversationSession | None = None,
        max_messages: int = 8,
        max_turn_memories: int = 4,
    ) -> "ResearchPilotBlackboard":
        """Build a blackboard from the current user request and conversation session."""

        if session is None:
            return cls(user_request=user_request)

        board = cls(
            user_request=user_request,
            session_id=session.session_id,
            session_summary=session.summary,
            recent_messages=[
                message.model_dump()
                for message in session.recent_messages(max_messages)
            ],
        )

        board.recent_turn_memories = cls._extract_recent_turn_memories(
            session=session,
            max_turn_memories=max_turn_memories,
        )

        board._merge_turn_memories(board.recent_turn_memories)

        return board

    def add_note(
        self,
        author: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Add a note to the shared blackboard."""

        self.notes.append(
            BlackboardNote(
                author=author,
                content=content,
                metadata=metadata or {},
            )
        )

    def merge_agent_state(self, state: AgentState) -> None:
        """Merge useful evidence and metadata from one AgentState."""

        evidence_store = getattr(state, "evidence_store", None)

        if evidence_store is not None:
            items = getattr(evidence_store, "items", [])

            for item in items:
                self._add_evidence_item(item)

        for step in state.steps:
            action = step.action
            observation = step.observation

            tool_name = action.tool_name
            tool_input = action.tool_input or {}

            if tool_name == "code_search":
                query = tool_input.get("query")
                if query:
                    self.code_search_queries.append(str(query))

            if tool_name == "code_read":
                path = tool_input.get("path")
                if path:
                    self.code_files.append(str(path))

            if observation is not None and observation.metadata:
                self._merge_observation_metadata(
                    tool_name=tool_name or "",
                    metadata=observation.metadata,
                )

        self._dedupe_all()

    def compact_context(self) -> str:
        """Render a compact text context for subagents."""

        sections: list[str] = []

        sections.append(f"User request:\n{self.user_request}")

        if self.session_summary.strip():
            sections.append(f"Session summary:\n{self.session_summary.strip()}")

        if self.code_files:
            sections.append(
                "Code files:\n"
                + "\n".join(f"- {file}" for file in self.code_files[:20])
            )

        if self.code_search_queries:
            sections.append(
                "Code search queries:\n"
                + "\n".join(f"- {query}" for query in self.code_search_queries[:20])
            )

        if self.evidence_sources:
            sections.append(
                "Evidence sources:\n"
                + "\n".join(f"- {source}" for source in self.evidence_sources[:30])
            )

        if self.report_paths:
            sections.append(
                "Report paths:\n"
                + "\n".join(f"- {path}" for path in self.report_paths[:20])
            )

        if self.notes:
            note_lines = []
            for note in self.notes[-10:]:
                note_lines.append(f"- {note.author}: {note.content}")
            sections.append("Subagent notes:\n" + "\n".join(note_lines))

        return "\n\n---\n\n".join(sections)

    def _add_evidence_item(self, item: EvidenceItem) -> None:
        source = getattr(item, "source", "")
        content = getattr(item, "content", "")
        metadata = getattr(item, "metadata", {}) or {}

        if source:
            self.evidence_sources.append(str(source))

        self.evidence_items.append(
            {
                "source": source,
                "content_preview": str(content)[:1000],
                "metadata": metadata,
            }
        )

    def _merge_observation_metadata(
        self,
        tool_name: str,
        metadata: dict[str, Any],
    ) -> None:
        file = metadata.get("file")
        if file:
            self.code_files.append(str(file))

        path = metadata.get("path")
        if path and tool_name in {"code_read", "read_file"}:
            self.code_files.append(str(path))

        report_path = metadata.get("report_path") or metadata.get("saved_path")
        if report_path:
            self.report_paths.append(str(report_path))

        matches = metadata.get("matches")
        if isinstance(matches, list):
            for match in matches[:10]:
                if not isinstance(match, dict):
                    continue

                match_file = match.get("file")
                if match_file:
                    self.code_files.append(str(match_file))

    def _merge_turn_memories(self, memories: list[dict[str, Any]]) -> None:
        for memory in memories:
            self.code_files.extend(memory.get("code_files") or [])
            self.code_search_queries.extend(memory.get("code_search_queries") or [])
            self.evidence_sources.extend(memory.get("evidence_sources") or [])
            self.report_paths.extend(memory.get("report_paths") or [])

        self._dedupe_all()

    def _dedupe_all(self) -> None:
        self.code_files = self._dedupe(self.code_files)
        self.code_search_queries = self._dedupe(self.code_search_queries)
        self.evidence_sources = self._dedupe(self.evidence_sources)
        self.report_paths = self._dedupe(self.report_paths)

    @staticmethod
    def _extract_recent_turn_memories(
        session: ConversationSession,
        max_turn_memories: int,
    ) -> list[dict[str, Any]]:
        memories: list[dict[str, Any]] = []

        for message in reversed(session.messages):
            if message.role != "assistant":
                continue

            memory = message.metadata.get("turn_memory")
            if isinstance(memory, dict):
                memories.append(memory)

            if len(memories) >= max_turn_memories:
                break

        memories.reverse()
        return memories

    @staticmethod
    def _dedupe(items: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []

        for item in items:
            normalized = str(item).strip()
            if not normalized:
                continue

            key = normalized.lower().replace("\\", "/")
            if key in seen:
                continue

            seen.add(key)
            result.append(normalized)

        return result