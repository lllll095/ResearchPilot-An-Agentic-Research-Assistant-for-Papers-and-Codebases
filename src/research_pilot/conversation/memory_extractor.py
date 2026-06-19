# src/research_pilot/conversation/memory_extractor.py

"""Extract key facts from conversations and store them in long-term memory."""

import re
from typing import Any

from research_pilot.conversation.session import ConversationSession
from research_pilot.memory.long_term_memory import LongTermMemoryStore


class MemoryExtractor:
    """Extract and store key facts from conversations.

    This provides a simple heuristic-based extraction:
    - "My name is X" -> store user_name = X
    - "I am working on X" -> store project = X
    - "I like/prefer X" -> store preference = X

    For production use, this should be replaced with an LLM-based extractor.
    """

    def __init__(self, memory_store: LongTermMemoryStore):
        self.memory_store = memory_store

        # Simple patterns for fact extraction
        self.patterns: list[tuple[str, str, float]] = [
            # (regex, key_template, confidence)
            (r"my name is (\w+)", "user_name:{0}", 0.9),
            (r"I am (\w+)", "user_name:{0}", 0.7),
            (r"call me (\w+)", "user_name:{0}", 0.8),
            (r"I am working on (.+)", "project:{0}", 0.8),
            (r"my project is (.+)", "project:{0}", 0.9),
            (r"I am researching (.+)", "research_topic:{0}", 0.8),
            (r"I study (.+)", "research_topic:{0}", 0.7),
            (r"I prefer (.+)", "preference:{0}", 0.7),
            (r"I like (.+)", "preference:{0}", 0.6),
            (r"I use (.+)", "tool:{0}", 0.6),
        ]

    def extract_from_session(
        self,
        session: ConversationSession,
        tags: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Extract facts from all messages in a session and store them."""
        extracted: list[dict[str, Any]] = []

        for message in session.messages:
            if message.role == "user":
                facts = self._extract_from_text(message.content)
                for fact in facts:
                    self.memory_store.save(
                        key=fact["key"],
                        value=fact["value"],
                        source_session=session.session_id,
                        confidence=fact["confidence"],
                        tags=tags or ["conversation"],
                    )
                    extracted.append(fact)

        return extracted

    def _extract_from_text(self, text: str) -> list[dict[str, Any]]:
        """Extract facts from a single text string."""
        facts: list[dict[str, Any]] = []

        for pattern, key_template, confidence in self.patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0]
                key = key_template.format(match.strip())
                # Normalize key: lowercase, replace spaces with underscores
                key = key.lower().replace(" ", "_").replace("-", "_")
                facts.append({
                    "key": key,
                    "value": match.strip(),
                    "confidence": confidence,
                })

        return facts
