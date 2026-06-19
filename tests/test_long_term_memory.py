"""Tests for LongTermMemoryStore."""

import json
from pathlib import Path

from research_pilot.memory.long_term_memory import LongTermMemoryStore, MemoryItem


class TestLongTermMemoryStore:
    """Tests for the SQLite-backed long-term memory store."""

    def test_save_and_get(self, tmp_path: Path):
        store = LongTermMemoryStore(tmp_path / "test_memory.db")

        store.save(key="user_name", value="Alice", source_session="session_1", confidence=0.9)

        item = store.get("user_name")
        assert item is not None
        assert item.key == "user_name"
        assert item.value == "Alice"
        assert item.source_session == "session_1"
        assert item.confidence == 0.9

        store.close()

    def test_get_nonexistent(self, tmp_path: Path):
        store = LongTermMemoryStore(tmp_path / "test_memory.db")

        item = store.get("nonexistent")
        assert item is None

        store.close()

    def test_upsert_updates_value(self, tmp_path: Path):
        store = LongTermMemoryStore(tmp_path / "test_memory.db")

        store.save(key="topic", value="DetectGPT")
        store.save(key="topic", value="Agentic RAG", confidence=0.8)

        item = store.get("topic")
        assert item.value == "Agentic RAG"
        assert item.confidence == 0.8

        store.close()

    def test_retrieve_by_keyword(self, tmp_path: Path):
        store = LongTermMemoryStore(tmp_path / "test_memory.db")

        store.save(key="research_topic", value="Agentic RAG")
        store.save(key="preferred_language", value="Chinese")

        results = store.retrieve("RAG", top_k=5)
        assert len(results) >= 1
        assert results[0].key == "research_topic"

        store.close()

    def test_retrieve_by_value(self, tmp_path: Path):
        store = LongTermMemoryStore(tmp_path / "test_memory.db")

        store.save(key="topic", value="DetectGPT detection methods")

        results = store.retrieve("DetectGPT", top_k=5)
        assert len(results) >= 1

        store.close()

    def test_save_with_tags(self, tmp_path: Path):
        store = LongTermMemoryStore(tmp_path / "test_memory.db")

        store.save(key="project", value="ResearchPilot", tags=["agent", "research", "rag"])

        item = store.get("project")
        assert "agent" in item.tags
        assert "research" in item.tags

        store.close()

    def test_retrieve_by_tags(self, tmp_path: Path):
        store = LongTermMemoryStore(tmp_path / "test_memory.db")

        store.save(key="a", value="Alpha", tags=["code"])
        store.save(key="b", value="Beta", tags=["paper"])
        store.save(key="c", value="Gamma", tags=["code", "paper"])

        results = store.retrieve_by_tags(["code"], top_k=5)
        keys = [r.key for r in results]
        assert "a" in keys
        assert "c" in keys

        store.close()

    def test_format_for_context(self, tmp_path: Path):
        store = LongTermMemoryStore(tmp_path / "test_memory.db")

        store.save(key="name", value="Alice", confidence=0.9)
        store.save(key="lang", value="Chinese", confidence=0.8)

        context = store.format_for_context(top_k=10)

        assert "Previous conversation memories:" in context
        assert "Alice" in context
        assert "Chinese" in context

        store.close()

    def test_empty_format(self, tmp_path: Path):
        store = LongTermMemoryStore(tmp_path / "test_memory.db")

        context = store.format_for_context()
        assert context == ""

        store.close()

    def test_delete(self, tmp_path: Path):
        store = LongTermMemoryStore(tmp_path / "test_memory.db")

        store.save(key="temp", value="delete me")
        store.delete("temp")

        assert store.get("temp") is None

        store.close()

    def test_count(self, tmp_path: Path):
        store = LongTermMemoryStore(tmp_path / "test_memory.db")

        assert store.count() == 0

        store.save(key="a", value="1")
        store.save(key="b", value="2")
        store.save(key="c", value="3")

        assert store.count() == 3

        store.close()

    def test_clear(self, tmp_path: Path):
        store = LongTermMemoryStore(tmp_path / "test_memory.db")

        store.save(key="x", value="1")
        store.clear()

        assert store.count() == 0

        store.close()

    def test_all_ordered_by_update(self, tmp_path: Path):
        store = LongTermMemoryStore(tmp_path / "test_memory.db")

        store.save(key="first", value="old")
        import time
        time.sleep(0.01)
        store.save(key="second", value="new")

        all_items = store.all(top_k=10)
        assert all_items[0].key == "second"

        store.close()
