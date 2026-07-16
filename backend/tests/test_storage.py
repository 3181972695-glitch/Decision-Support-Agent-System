"""Tests for the storage layer (DebateRepository implementations).

All tests are written against the abstract DebateRepository interface
so they apply equally to every concrete implementation.
"""

from __future__ import annotations

import uuid

import pytest

from app.domain.debate import Debate, Round, Verdict
from app.domain.enums import DebateStatus
from app.storage.in_memory import InMemoryDebateRepository
from app.storage.repository import DebateRepository


# =================================================================
#  Fixtures
# =================================================================


@pytest.fixture
def repo() -> DebateRepository:
    """Provide a fresh in-memory repository for each test."""
    return InMemoryDebateRepository()


@pytest.fixture
def sample_debate() -> Debate:
    """A minimal Debate instance for use in persistence tests."""
    return Debate(id="debate-1", topic="Should I learn Rust?")


# =================================================================
#  Constructor
# =================================================================


class TestRepositoryCreation:
    """The repository starts in a known empty state."""

    async def test_new_repository_is_empty(self, repo: DebateRepository) -> None:
        assert await repo.list() == []
        assert await repo.exists("anything") is False
        assert await repo.get("anything") is None


# =================================================================
#  save() + get()
# =================================================================


class TestSaveAndGet:
    """Persisting and retrieving a single debate."""

    async def test_save_and_get(
        self, repo: DebateRepository, sample_debate: Debate
    ) -> None:
        await repo.save(sample_debate)
        retrieved = await repo.get(sample_debate.id)
        assert retrieved is not None
        assert retrieved.id == "debate-1"
        assert retrieved.topic == "Should I learn Rust?"
        assert retrieved is not sample_debate  # deep copy

    async def test_get_returns_same_object(
        self, repo: DebateRepository, sample_debate: Debate
    ) -> None:
        """get returns a copy with identical values."""
        await repo.save(sample_debate)
        retrieved = await repo.get("debate-1")
        assert retrieved is not None
        # Deep copy semantics: values match but object is different
        assert retrieved.id == sample_debate.id
        assert retrieved.topic == sample_debate.topic
        assert retrieved is not sample_debate

    async def test_get_returns_none_for_missing(self, repo: DebateRepository) -> None:
        assert await repo.get("i-do-not-exist") is None

    async def test_get_returns_none_after_delete(
        self, repo: DebateRepository, sample_debate: Debate
    ) -> None:
        await repo.save(sample_debate)
        await repo.delete(sample_debate.id)
        assert await repo.get(sample_debate.id) is None

    async def test_save_overwrites_existing(self, repo: DebateRepository) -> None:
        original = Debate(id="dup-1", topic="Original topic")
        await repo.save(original)

        replacement = Debate(id="dup-1", topic="Updated topic")
        await repo.save(replacement)

        retrieved = await repo.get("dup-1")
        assert retrieved is not None
        assert retrieved is not replacement  # deep copy
        assert retrieved.topic == "Updated topic"
        assert len(await repo.list()) == 1

    async def test_save_with_different_ids_keeps_both(
        self, repo: DebateRepository
    ) -> None:
        a = Debate(id="a", topic="Topic A")
        b = Debate(id="b", topic="Topic B")
        await repo.save(a)
        await repo.save(b)
        assert await repo.get("a") is not None
        assert await repo.get("b") is not None
        assert (await repo.get("a")).id == "a"
        assert (await repo.get("b")).id == "b"
        assert len(await repo.list()) == 2

    async def test_get_is_immutable_on_repo(
        self, repo: DebateRepository, sample_debate: Debate
    ) -> None:
        """Retrieving does not mutate the repository state."""
        await repo.save(sample_debate)
        _ = await repo.get("debate-1")
        assert await repo.exists("debate-1") is True
        assert len(await repo.list()) == 1



    async def test_get_returns_copy_mutation_is_safe(
        self, repo: DebateRepository, sample_debate: Debate
    ) -> None:
        """Mutations to a retrieved object do not affect the stored state."""
        await repo.save(sample_debate)
        retrieved = await repo.get("debate-1")
        assert retrieved is not None
        retrieved.topic = "Mutated topic"
        # Re-fetch — should still be original
        fresh = await repo.get("debate-1")
        assert fresh is not None
        assert fresh.topic == "Should I learn Rust?"
        assert fresh.topic != "Mutated topic"

    async def test_save_stores_copy_mutation_is_safe(
        self, repo: DebateRepository, sample_debate: Debate
    ) -> None:
        """Mutations to a saved object after save() do not affect the stored state."""
        await repo.save(sample_debate)
        sample_debate.topic = "Mutated after save"
        fresh = await repo.get("debate-1")
        assert fresh is not None
        assert fresh.topic == "Should I learn Rust?"

# =================================================================
#  list()
# =================================================================


class TestList:
    """Listing all stored debates."""

    async def test_list_empty(self, repo: DebateRepository) -> None:
        assert await repo.list() == []

    async def test_list_single(
        self, repo: DebateRepository, sample_debate: Debate
    ) -> None:
        await repo.save(sample_debate)
        assert await repo.list() == [sample_debate]

    async def test_list_multiple(self, repo: DebateRepository) -> None:
        debates = [
            Debate(id="d1", topic="Topic 1"),
            Debate(id="d2", topic="Topic 2"),
            Debate(id="d3", topic="Topic 3"),
        ]
        for d in debates:
            await repo.save(d)
        assert await repo.list() == debates

    async def test_list_maintains_insertion_order(self, repo: DebateRepository) -> None:
        await repo.save(Debate(id="z", topic="Last alphabetically"))
        await repo.save(Debate(id="a", topic="First alphabetically"))
        await repo.save(Debate(id="m", topic="Middle"))
        ids = [d.id for d in await repo.list()]
        assert ids == ["z", "a", "m"]

    async def test_list_reflects_overwrites(self, repo: DebateRepository) -> None:
        d = Debate(id="d1", topic="Old")
        await repo.save(d)
        d2 = Debate(id="d1", topic="New")
        await repo.save(d2)
        assert await repo.list() == [d2]

    async def test_list_returns_copy(
        self, repo: DebateRepository, sample_debate: Debate
    ) -> None:
        """Modifying the returned list should not affect the repository."""
        await repo.save(sample_debate)
        result = await repo.list()
        result.clear()
        assert await repo.exists("debate-1") is True
        assert len(await repo.list()) == 1


# =================================================================
#  delete()
# =================================================================


class TestDelete:
    """Removing debates from the repository."""

    async def test_delete_existing(
        self, repo: DebateRepository, sample_debate: Debate
    ) -> None:
        await repo.save(sample_debate)
        await repo.delete(sample_debate.id)
        assert await repo.exists(sample_debate.id) is False
        assert sample_debate not in await repo.list()

    async def test_delete_missing_is_noop(self, repo: DebateRepository) -> None:
        """Deleting a non-existent id should not raise."""
        await repo.delete("i-do-not-exist")  # no exception
        assert await repo.list() == []

    async def test_delete_missing_does_not_affect_others(
        self, repo: DebateRepository
    ) -> None:
        await repo.save(Debate(id="keep", topic="Keep me"))
        await repo.delete("nonexistent")
        assert len(await repo.list()) == 1
        assert await repo.get("keep") is not None

    async def test_delete_then_list(self, repo: DebateRepository) -> None:
        await repo.save(Debate(id="d1", topic="T1"))
        await repo.save(Debate(id="d2", topic="T2"))
        await repo.delete("d1")
        ids = [d.id for d in await repo.list()]
        assert ids == ["d2"]

    async def test_delete_then_save_same_id(self, repo: DebateRepository) -> None:
        d = Debate(id="d1", topic="T1")
        await repo.save(d)
        await repo.delete("d1")
        d2 = Debate(id="d1", topic="T2")
        await repo.save(d2)
        assert await repo.get("d1") is not None
        assert len(await repo.list()) == 1

    async def test_delete_idempotent(self, repo: DebateRepository) -> None:
        await repo.save(Debate(id="d1", topic="T1"))
        await repo.delete("d1")
        await repo.delete("d1")  # second delete should be safe
        assert await repo.exists("d1") is False


# =================================================================
#  exists()
# =================================================================


class TestExists:
    """Checking whether a debate exists."""

    async def test_exists_returns_true_when_present(
        self, repo: DebateRepository, sample_debate: Debate
    ) -> None:
        await repo.save(sample_debate)
        assert await repo.exists(sample_debate.id) is True

    async def test_exists_returns_false_when_absent(
        self, repo: DebateRepository
    ) -> None:
        assert await repo.exists("never-saved") is False

    async def test_exists_returns_false_after_delete(
        self, repo: DebateRepository, sample_debate: Debate
    ) -> None:
        await repo.save(sample_debate)
        await repo.delete(sample_debate.id)
        assert await repo.exists(sample_debate.id) is False

    async def test_exists_with_empty_string_id(self, repo: DebateRepository) -> None:
        debate = Debate(id="", topic="Empty ID")
        await repo.save(debate)
        assert await repo.exists("") is True

    async def test_exists_after_overwrite(self, repo: DebateRepository) -> None:
        await repo.save(Debate(id="d1", topic="Old"))
        await repo.save(Debate(id="d1", topic="New"))
        assert await repo.exists("d1") is True


# =================================================================
#  Edge cases
# =================================================================


class TestStorageEdgeCases:
    """Unusual but valid usage patterns."""

    async def test_uuid_ids(self, repo: DebateRepository) -> None:
        uid = str(uuid.uuid4())
        d = Debate(id=uid, topic="UUID topic")
        await repo.save(d)
        assert await repo.get(uid) is not None
        assert await repo.exists(uid) is True

    async def test_special_character_ids(self, repo: DebateRepository) -> None:
        d = Debate(id="id-with/slashes and spaces!", topic="Funky ID")
        await repo.save(d)
        assert await repo.get(d.id) is not None

    async def test_very_long_ids(self, repo: DebateRepository) -> None:
        long_id = "x" * 1000
        d = Debate(id=long_id, topic="Long ID")
        await repo.save(d)
        assert await repo.get(long_id) is not None

    async def test_numeric_string_ids(self, repo: DebateRepository) -> None:
        d = Debate(id="42", topic="Numeric ID")
        await repo.save(d)
        assert await repo.get("42") is not None

    async def test_debate_with_complex_state(self, repo: DebateRepository) -> None:
        """A fully populated debate round-trips correctly."""

        debate = Debate(id="complex-1", topic="Complex debate?")
        debate.advance_status(DebateStatus.IN_PROGRESS)

        for i in range(1, 4):
            from app.domain.debate import Argument
            from app.domain.enums import AgentRole

            r = Round(
                round_number=i,
                moderator_summary=f"Summary {i}",
                moderator_steer=f"Steer {i}",
                pro_opening=Argument(role=AgentRole.PRO, content=f"Pro point {i}"),
                con_opening=Argument(role=AgentRole.CON, content=f"Con point {i}"),
            )
            debate.add_round(r)

        debate.set_verdict(
            Verdict(summary="Final summary", recommendation="Final rec.")
        )

        await repo.save(debate)
        retrieved = await repo.get("complex-1")
        assert retrieved is not None
        assert retrieved.topic == "Complex debate?"
        assert retrieved.status == DebateStatus.COMPLETED
        assert len(retrieved.rounds) == 3
        assert retrieved.verdict is not None
        assert retrieved.verdict.summary == "Final summary"
        assert retrieved.verdict.recommendation == "Final rec."
        assert retrieved.rounds[1].pro_opening is not None
        assert retrieved.rounds[1].pro_opening.content == "Pro point 2"

    async def test_delete_after_save_same_reference(
        self, repo: DebateRepository, sample_debate: Debate
    ) -> None:
        await repo.save(sample_debate)
        await repo.delete(sample_debate.id)
        # Re-saving the same object instance should make it retrievable
        await repo.save(sample_debate)
        assert await repo.get(sample_debate.id) is not None

    async def test_list_reflects_multiple_operations(
        self, repo: DebateRepository
    ) -> None:
        d1 = Debate(id="d1", topic="T1")
        d2 = Debate(id="d2", topic="T2")
        d3 = Debate(id="d3", topic="T3")

        await repo.save(d1)
        await repo.save(d2)
        await repo.save(d3)
        assert len(await repo.list()) == 3

        await repo.delete("d2")
        assert len(await repo.list()) == 2
        assert await repo.list() == [d1, d3]

        await repo.save(Debate(id="d4", topic="T4"))
        assert len(await repo.list()) == 3
        assert [d.id for d in await repo.list()] == ["d1", "d3", "d4"]

    async def test_repository_state_is_isolated(self, repo: DebateRepository) -> None:
        """Each repository instance has its own state."""
        repo2 = InMemoryDebateRepository()
        await repo.save(Debate(id="a", topic="Repo 1"))
        await repo2.save(Debate(id="b", topic="Repo 2"))
        assert len(await repo.list()) == 1
        assert len(await repo2.list()) == 1
        assert await repo.get("a") is not None
        assert await repo2.get("a") is None
