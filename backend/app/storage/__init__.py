"""Storage layer — repository implementations and factory."""

from app.config import settings
from app.storage.in_memory import InMemoryDebateRepository
from app.storage.repository import DebateRepository
from app.storage.sql_repository import SqlDebateRepository


async def create_repository() -> DebateRepository:
    """Async factory: return and initialize the configured repository.

    For SQL backend, this awaits _init_db() to create tables.
    For memory backend, this returns immediately.
    """
    if settings.DB_BACKEND == "sql":
        repo = SqlDebateRepository(database_url=settings.DATABASE_URL)
        await repo._init_db()
        return repo

    return InMemoryDebateRepository()
