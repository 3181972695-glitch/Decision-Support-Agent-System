"""In-memory implementation of DebateRepository.

Uses a plain dict keyed by debate id. Suitable for prototyping and
testing — swap for a database-backed implementation when needed.
"""

from app.domain.debate import Debate
from app.storage.repository import DebateRepository


class InMemoryDebateRepository(DebateRepository):
    """Stores debates in a dict. Insertion-order preserving (Python 3.7+)."""

    def __init__(self) -> None:
        self._store: dict[str, Debate] = {}

    def save(self, debate: Debate) -> None:
        """Persist a debate, creating or overwriting by id."""
        self._store[debate.id] = debate

    def get(self, debate_id: str) -> Debate | None:
        """Return the debate or None when not found."""
        return self._store.get(debate_id)

    def list(self) -> list[Debate]:
        """Return all debates in insertion order."""
        return list(self._store.values())

    def delete(self, debate_id: str) -> None:
        """Remove a debate. Silent no-op on missing id."""
        self._store.pop(debate_id, None)

    def exists(self, debate_id: str) -> bool:
        """Return True when the debate id is present."""
        return debate_id in self._store
