"""Shared contract tests for all DebateRepository implementations.

Every repository implementation must pass these tests. Add new
implementations by adding them to the `repositories` fixture.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.domain.debate import Argument, Debate, Round, Verdict
from app.domain.enums import AgentRole, DebateStatus
from app.storage.in_memory import InMemoryDebateRepository
from app.storage.repository import DebateRepository
from app.storage.sql_repository import SqlDebateRepository


@pytest.fixture(params=["memory", "sql"])
async def repo(request: pytest.FixtureRequest) -> DebateRepository:
    """Provide each repository implementation for contract testing."""
    if request.param == "memory":
        return InMemoryDebateRepository()
    else:
        tmpdir = tempfile.mkdtemp()
        db_path = Path(tmpdir) / "test.db"
        repo = SqlDebateRepository(database_url=f"sqlite+aiosqlite:///{db_path}")

        await repo._init_db()
        return repo


@pytest.fixture
def sample_debate() -> Debate:
    return Debate(id="debate-1", topic="Should I learn Rust?")


class TestRepositoryCreation:
    async def test_new_repository_is_empty(self, repo: DebateRepository) -> None:
        assert await repo.list() == []
        assert await repo.exists("anything") is False
        assert await repo.get("anything") is None


class TestSaveAndGet:
    async def test_save_and_get(
        self, repo: DebateRepository, sample_debate: Debate
    ) -> None:
        await repo.save(sample_debate)
        retrieved = await repo.get(sample_debate.id)
        assert retrieved is not None
        assert retrieved.id == "debate-1"
        assert retrieved.topic == "Should I learn Rust?"

    async def test_get_returns_none_for_missing(self, repo: DebateRepository) -> None:
        assert await repo.get("i-do-not-exist") is None

    async def test_get_returns_none_after_delete(
        self, repo: DebateRepository, sample_debate: Debate
    ) -> None:
        await repo.save(sample_debate)
        await repo.delete(sample_debate.id)
        assert await repo.get(sample_debate.id) is None

    async def test_save_overwrites_existing(self, repo: DebateRepository) -> None:
        await repo.save(Debate(id="dup-1", topic="Original"))
        await repo.save(Debate(id="dup-1", topic="Updated"))
        retrieved = await repo.get("dup-1")
        assert retrieved is not None
        assert retrieved.topic == "Updated"
        assert len(await repo.list()) == 1

    async def test_save_with_different_ids_keeps_both(
        self, repo: DebateRepository
    ) -> None:
        a = Debate(id="a", topic="A")
        b = Debate(id="b", topic="B")
        await repo.save(a)
        await repo.save(b)
        assert await repo.get("a") is not None
        assert await repo.get("b") is not None
        assert len(await repo.list()) == 2


class TestList:
    async def test_list_empty(self, repo: DebateRepository) -> None:
        assert await repo.list() == []

    async def test_list_single(
        self, repo: DebateRepository, sample_debate: Debate
    ) -> None:
        await repo.save(sample_debate)
        listed = await repo.list()
        assert len(listed) == 1
        assert listed[0].id == sample_debate.id

    async def test_list_multiple(self, repo: DebateRepository) -> None:
        debates = [
            Debate(id="d1", topic="T1"),
            Debate(id="d2", topic="T2"),
            Debate(id="d3", topic="T3"),
        ]
        for d in debates:
            await repo.save(d)
        ids = [d.id for d in await repo.list()]
        assert ids == ["d1", "d2", "d3"]


class TestDelete:
    async def test_delete_existing(
        self, repo: DebateRepository, sample_debate: Debate
    ) -> None:
        await repo.save(sample_debate)
        await repo.delete(sample_debate.id)
        assert await repo.exists(sample_debate.id) is False

    async def test_delete_missing_is_noop(self, repo: DebateRepository) -> None:
        await repo.delete("never-saved")  # should not raise

    async def test_delete_idempotent(
        self, repo: DebateRepository, sample_debate: Debate
    ) -> None:
        await repo.save(sample_debate)
        await repo.delete(sample_debate.id)
        await repo.delete(sample_debate.id)  # should not raise


class TestExists:
    async def test_exists_true(
        self, repo: DebateRepository, sample_debate: Debate
    ) -> None:
        await repo.save(sample_debate)
        assert await repo.exists(sample_debate.id) is True

    async def test_exists_false(self, repo: DebateRepository) -> None:
        assert await repo.exists("never-saved") is False

    async def test_exists_false_after_delete(
        self, repo: DebateRepository, sample_debate: Debate
    ) -> None:
        await repo.save(sample_debate)
        await repo.delete(sample_debate.id)
        assert await repo.exists(sample_debate.id) is False


class TestComplexState:
    """Round-trip of a fully populated debate."""

    async def test_complex_debate_round_trips(self, repo: DebateRepository) -> None:
        debate = Debate(id="complex-1", topic="Complex debate?")
        debate.advance_status(DebateStatus.IN_PROGRESS)

        for i in range(1, 4):
            r = Round(
                round_number=i,
                moderator_summary=f"Summary {i}",
                moderator_steer=f"Steer {i}",
                pro_opening=Argument(role=AgentRole.PRO, content=f"Pro {i}"),
                con_opening=Argument(role=AgentRole.CON, content=f"Con {i}"),
            )
            debate.add_round(r)

        debate.set_verdict(Verdict(summary="Final", recommendation="Rec"))

        await repo.save(debate)
        retrieved = await repo.get("complex-1")
        assert retrieved is not None
        assert retrieved.topic == "Complex debate?"
        assert retrieved.status == DebateStatus.COMPLETED
        assert len(retrieved.rounds) == 3
        assert retrieved.verdict is not None
        assert retrieved.verdict.summary == "Final"
        assert retrieved.rounds[1].pro_opening is not None
        assert retrieved.rounds[1].pro_opening.content == "Pro 2"
