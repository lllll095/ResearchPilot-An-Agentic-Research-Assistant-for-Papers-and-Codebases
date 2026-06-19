# src/research_pilot/memory/long_term_memory.py

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class MemoryItem(BaseModel):
    """A single fact stored in long-term memory."""

    key: str
    value: str
    source_session: str = ""
    created_at: str = ""
    updated_at: str = ""
    confidence: float = 0.5
    tags: list[str] = Field(default_factory=list)


class LongTermMemoryStore:
    """SQLite-backed persistent key-value memory store.

    Stores facts extracted from conversations across sessions.
    Supports keyword-based retrieval and context formatting for LLM injection.
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._init_db()

    def _init_db(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                source_session TEXT DEFAULT "",
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                confidence REAL DEFAULT 0.5,
                tags TEXT DEFAULT "[]"
            )
        """)
        self._conn.commit()

    def save(
        self,
        key: str,
        value: str,
        source_session: str = "",
        confidence: float = 0.5,
        tags: list[str] | None = None,
    ) -> None:
        """Upsert a memory fact."""
        now = datetime.now().isoformat()
        tags_json = json.dumps(tags or [], ensure_ascii=False)
        self._conn.execute(
            """
            INSERT INTO memories (key, value, source_session, created_at, updated_at, confidence, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at,
                confidence = excluded.confidence,
                tags = excluded.tags
            """,
            (key, value, source_session, now, now, confidence, tags_json),
        )
        self._conn.commit()

    def get(self, key: str) -> MemoryItem | None:
        """Get a specific memory by key."""
        cursor = self._conn.execute(
            "SELECT key, value, source_session, created_at, updated_at, confidence, tags FROM memories WHERE key = ?",
            (key,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_item(row)

    def retrieve(self, query: str, top_k: int = 5) -> list[MemoryItem]:
        """Search memories by keyword matching in key and value."""
        cursor = self._conn.execute(
            "SELECT key, value, source_session, created_at, updated_at, confidence, tags FROM memories WHERE key LIKE ? OR value LIKE ? ORDER BY confidence DESC LIMIT ?",
            (f"%{query}%", f"%{query}%", top_k),
        )
        return [self._row_to_item(row) for row in cursor.fetchall()]

    def retrieve_by_tags(self, tags: list[str], top_k: int = 10) -> list[MemoryItem]:
        """Search memories by tags."""
        results = []
        for item in self.all(top_k=100):
            if any(t in item.tags for t in tags):
                results.append(item)
                if len(results) >= top_k:
                    break
        return results

    def all(self, top_k: int = 50) -> list[MemoryItem]:
        """Get all memories, newest first."""
        cursor = self._conn.execute(
            "SELECT key, value, source_session, created_at, updated_at, confidence, tags FROM memories ORDER BY updated_at DESC LIMIT ?",
            (top_k,),
        )
        return [self._row_to_item(row) for row in cursor.fetchall()]

    def format_for_context(self, top_k: int = 10, filter_tags: list[str] | None = None) -> str:
        """Format relevant memories for LLM context injection.

        Args:
            top_k: Maximum number of memories to include.
            filter_tags: If set, only include memories with these tags.

        Returns:
            A formatted string ready to inject into system prompt or blackboard context.
        """
        if filter_tags:
            items = self.retrieve_by_tags(filter_tags, top_k=top_k)
        else:
            items = self.all(top_k=top_k)

        if not items:
            return ""

        lines = ["Previous conversation memories:"]
        for item in items:
            tag_str = f" [{', '.join(item.tags)}]" if item.tags else ""
            lines.append(f"- {item.key}: {item.value} (confidence: {item.confidence:.1f}){tag_str}")
        lines.append("(Use these memories to provide continuity across conversations.)")

        return "\n".join(lines)

    def delete(self, key: str) -> None:
        """Delete a memory by key."""
        self._conn.execute("DELETE FROM memories WHERE key = ?", (key,))
        self._conn.commit()

    def count(self) -> int:
        """Number of stored memories."""
        cursor = self._conn.execute("SELECT COUNT(*) FROM memories")
        return cursor.fetchone()[0]

    def clear(self) -> None:
        """Delete all memories (for testing)."""
        self._conn.execute("DELETE FROM memories")
        self._conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def _row_to_item(self, row: tuple) -> MemoryItem:
        return MemoryItem(
            key=row[0],
            value=row[1],
            source_session=row[2],
            created_at=row[3],
            updated_at=row[4],
            confidence=float(row[5]),
            tags=json.loads(row[6]) if row[6] else [],
        )
