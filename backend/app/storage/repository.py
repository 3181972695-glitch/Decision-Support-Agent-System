"""Abstract repository interface for Debate persistence."""

from abc import ABC, abstractmethod

from app.domain.debate import Debate


class DebateRepository(ABC):
    """Abstract repository for Debate aggregate persistence.

    All concrete implementations must provide these five operations.
    Methods return domain objects directly — no DTO translation.
    """

    @abstractmethod
    def save(self, debate: Debate) -> None:
        """Persist a debate (create or overwrite by id)."""
        ...

    @abstractmethod
    def get(self, debate_id: str) -> Debate | None:
        """Retrieve a debate by id. Returns None when not found."""
        ...

    @abstractmethod
    def list(self) -> list[Debate]:
        """Return all stored debates in insertion order."""
        ...

    @abstractmethod
    def delete(self, debate_id: str) -> None:
        """Remove a debate by id. No-op if the id does not exist."""
        ...

    @abstractmethod
    def exists(self, debate_id: str) -> bool:
        """Return True when a debate with the given id is stored."""
        ...
