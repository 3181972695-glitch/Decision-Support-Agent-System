"""Abstract repository interface for Debate persistence."""

from abc import ABC, abstractmethod

from app.domain.debate import Debate


class DebateRepository(ABC):
    """Abstract repository for Debate aggregate persistence.

    All methods are async. Concrete implementations may use any
    backend (in-memory dict, SQLite, PostgreSQL, etc.).
    """

    @abstractmethod
    async def save(self, debate: Debate) -> None:
        """Persist a debate (create or overwrite by id)."""
        ...

    @abstractmethod
    async def get(self, debate_id: str) -> Debate | None:
        """Retrieve a debate by id. Returns None when not found."""
        ...

    @abstractmethod
    async def list(self) -> list[Debate]:
        """Return all stored debates in insertion order."""
        ...

    @abstractmethod
    async def delete(self, debate_id: str) -> None:
        """Remove a debate by id. No-op if the id does not exist."""
        ...

    @abstractmethod
    async def exists(self, debate_id: str) -> bool:
        """Return True when a debate with the given id is stored."""
        ...
