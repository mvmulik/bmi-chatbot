"""In-memory conversation history for follow-up questions."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock


@dataclass
class ConversationTurn:
    question: str
    answer: str


@dataclass
class ConversationStore:
    max_turns: int = 4
    _turns: dict[str, list[ConversationTurn]] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    def get(self, conversation_id: str) -> list[ConversationTurn]:
        with self._lock:
            return list(self._turns.get(conversation_id, []))

    def add(self, conversation_id: str, question: str, answer: str) -> None:
        if not conversation_id:
            return
        with self._lock:
            history = self._turns.setdefault(conversation_id, [])
            history.append(ConversationTurn(question=question, answer=answer))
            overflow = len(history) - self.max_turns
            if overflow > 0:
                del history[:overflow]

    def expand_query(self, conversation_id: str, message: str) -> str:
        """Keep follow-ups grounded in the previous BMI Hub question."""
        turns = self.get(conversation_id)
        if not turns:
            return message
        previous = turns[-1].question.strip()
        if not previous or previous.lower() == message.lower():
            return message
        return f"{message}\n\nPrevious question in this conversation: {previous}"

    def clear(self, conversation_id: str) -> None:
        with self._lock:
            self._turns.pop(conversation_id, None)


_store: ConversationStore | None = None


def get_conversation_store() -> ConversationStore:
    global _store
    if _store is None:
        _store = ConversationStore()
    return _store
