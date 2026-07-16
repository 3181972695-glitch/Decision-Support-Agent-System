"""In-memory implementation of DebateRepository.

Stores deep copies so callers cannot mutate shared state.
"""

import copy

from app.domain.debate import Debate
from app.storage.repository import DebateRepository


class InMemoryDebateRepository(DebateRepository):
    """Stores debates in a dict with deep-copy semantics.

    save() stores a deep copy and get() returns a deep copy,
    so mutations to returned objects do not affect the stored state.
    This matches the isolation behaviour of a real database.
    """

    def __init__(self) -> None:
        self._store: dict[str, Debate] = {}

    async def save(self, debate: Debate) -> None:
        self._store[debate.id] = copy.deepcopy(debate)

    async def get(self, debate_id: str) -> Debate | None:
        stored = self._store.get(debate_id)
        if stored is None:
            return None
        return copy.deepcopy(stored)

    async def list(self) -> list[Debate]:
        return [copy.deepcopy(v) for v in self._store.values()]

    async def delete(self, debate_id: str) -> None:
        self._store.pop(debate_id, None)

    async def exists(self, debate_id: str) -> bool:
        return debate_id in self._store
