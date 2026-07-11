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

    def test_new_repository_is_empty(self, repo: DebateRepository) -> None:
        assert repo.list() == []
        assert repo.exists("anything") is False
        assert repo.get("anything") is None


# =================================================================
#  save() + get()
# =================================================================


class TestSaveAndGet:
    """Persisting and retrieving a single debate."""

    def test_save_and_get(self, repo: DebateRepository, sample_debate: Debate) -> None:
        repo.save(sample_debate)
        retrieved = repo.get(sample_debate.id)
        assert retrieved is sample_debate
        assert retrieved.id == "debate-1"
        assert retrieved.topic == "Should I learn Rust?"

    def test_get_returns_same_object(
        self, repo: DebateRepository, sample_debate: Debate
    ) -> None:
        """Object identity: the repository stores and returns the same instance."""
        repo.save(sample_debate)
        retrieved = repo.get("debate-1")
        assert retrieved is sample_debate

    def test_get_returns_none_for_missing(self, repo: DebateRepository) -> None:
        assert repo.get("i-do-not-exist") is None

    def test_get_returns_none_after_delete(
        self, repo: DebateRepository, sample_debate: Debate
    ) -> None:
        repo.save(sample_debate)
        repo.delete(sample_debate.id)
        assert repo.get(sample_debate.id) is None

    def test_save_overwrites_existing(self, repo: DebateRepository) -> None:
        original = Debate(id="dup-1", topic="Original topic")
        repo.save(original)

        replacement = Debate(id="dup-1", topic="Updated topic")
        repo.save(replacement)

        retrieved = repo.get("dup-1")
        assert retrieved is replacement
        assert retrieved.topic == "Updated topic"
        assert len(repo.list()) == 1

    def test_save_with_different_ids_keeps_both(self, repo: DebateRepository) -> None:
        a = Debate(id="a", topic="Topic A")
        b = Debate(id="b", topic="Topic B")
        repo.save(a)
        repo.save(b)
        assert repo.get("a") is a
        assert repo.get("b") is b
        assert len(repo.list()) == 2

    def test_get_is_immutable_on_repo(
        self, repo: DebateRepository, sample_debate: Debate
    ) -> None:
        """Retrieving does not mutate the repository state."""
        repo.save(sample_debate)
        _ = repo.get("debate-1")
        assert repo.exists("debate-1") is True
        assert len(repo.list()) == 1


# =================================================================
#  list()
# =================================================================


class TestList:
    """Listing all stored debates."""

    def test_list_empty(self, repo: DebateRepository) -> None:
        assert repo.list() == []

    def test_list_single(self, repo: DebateRepository, sample_debate: Debate) -> None:
        repo.save(sample_debate)
        assert repo.list() == [sample_debate]

    def test_list_multiple(self, repo: DebateRepository) -> None:
        debates = [
            Debate(id="d1", topic="Topic 1"),
            Debate(id="d2", topic="Topic 2"),
            Debate(id="d3", topic="Topic 3"),
        ]
        for d in debates:
            repo.save(d)
        assert repo.list() == debates

    def test_list_maintains_insertion_order(self, repo: DebateRepository) -> None:
        repo.save(Debate(id="z", topic="Last alphabetically"))
        repo.save(Debate(id="a", topic="First alphabetically"))
        repo.save(Debate(id="m", topic="Middle"))
        ids = [d.id for d in repo.list()]
        assert ids == ["z", "a", "m"]

    def test_list_reflects_overwrites(self, repo: DebateRepository) -> None:
        d = Debate(id="d1", topic="Old")
        repo.save(d)
        d2 = Debate(id="d1", topic="New")
        repo.save(d2)
        assert repo.list() == [d2]

    def test_list_returns_copy(
        self, repo: DebateRepository, sample_debate: Debate
    ) -> None:
        """Modifying the returned list should not affect the repository."""
        repo.save(sample_debate)
        result = repo.list()
        result.clear()
        assert repo.exists("debate-1") is True
        assert len(repo.list()) == 1


# =================================================================
#  delete()
# =================================================================


class TestDelete:
    """Removing debates from the repository."""

    def test_delete_existing(
        self, repo: DebateRepository, sample_debate: Debate
    ) -> None:
        repo.save(sample_debate)
        repo.delete(sample_debate.id)
        assert repo.exists(sample_debate.id) is False
        assert sample_debate not in repo.list()

    def test_delete_missing_is_noop(self, repo: DebateRepository) -> None:
        """Deleting a non-existent id should not raise."""
        repo.delete("i-do-not-exist")  # no exception
        assert repo.list() == []

    def test_delete_missing_does_not_affect_others(
        self, repo: DebateRepository
    ) -> None:
        repo.save(Debate(id="keep", topic="Keep me"))
        repo.delete("nonexistent")
        assert len(repo.list()) == 1
        assert repo.get("keep") is not None

    def test_delete_then_list(self, repo: DebateRepository) -> None:
        repo.save(Debate(id="d1", topic="T1"))
        repo.save(Debate(id="d2", topic="T2"))
        repo.delete("d1")
        ids = [d.id for d in repo.list()]
        assert ids == ["d2"]

    def test_delete_then_save_same_id(self, repo: DebateRepository) -> None:
        d = Debate(id="d1", topic="T1")
        repo.save(d)
        repo.delete("d1")
        d2 = Debate(id="d1", topic="T2")
        repo.save(d2)
        assert repo.get("d1") is d2
        assert len(repo.list()) == 1

    def test_delete_idempotent(self, repo: DebateRepository) -> None:
        repo.save(Debate(id="d1", topic="T1"))
        repo.delete("d1")
        repo.delete("d1")  # second delete should be safe
        assert repo.exists("d1") is False


# =================================================================
#  exists()
# =================================================================


class TestExists:
    """Checking whether a debate exists."""

    def test_exists_returns_true_when_present(
        self, repo: DebateRepository, sample_debate: Debate
    ) -> None:
        repo.save(sample_debate)
        assert repo.exists(sample_debate.id) is True

    def test_exists_returns_false_when_absent(self, repo: DebateRepository) -> None:
        assert repo.exists("never-saved") is False

    def test_exists_returns_false_after_delete(
        self, repo: DebateRepository, sample_debate: Debate
    ) -> None:
        repo.save(sample_debate)
        repo.delete(sample_debate.id)
        assert repo.exists(sample_debate.id) is False

    def test_exists_with_empty_string_id(self, repo: DebateRepository) -> None:
        debate = Debate(id="", topic="Empty ID")
        repo.save(debate)
        assert repo.exists("") is True

    def test_exists_after_overwrite(self, repo: DebateRepository) -> None:
        repo.save(Debate(id="d1", topic="Old"))
        repo.save(Debate(id="d1", topic="New"))
        assert repo.exists("d1") is True


# =================================================================
#  Edge cases
# =================================================================


class TestStorageEdgeCases:
    """Unusual but valid usage patterns."""

    def test_uuid_ids(self, repo: DebateRepository) -> None:
        uid = str(uuid.uuid4())
        d = Debate(id=uid, topic="UUID topic")
        repo.save(d)
        assert repo.get(uid) is d
        assert repo.exists(uid) is True

    def test_special_character_ids(self, repo: DebateRepository) -> None:
        d = Debate(id="id-with/slashes and spaces!", topic="Funky ID")
        repo.save(d)
        assert repo.get(d.id) is d

    def test_very_long_ids(self, repo: DebateRepository) -> None:
        long_id = "x" * 1000
        d = Debate(id=long_id, topic="Long ID")
        repo.save(d)
        assert repo.get(long_id) is d

    def test_numeric_string_ids(self, repo: DebateRepository) -> None:
        d = Debate(id="42", topic="Numeric ID")
        repo.save(d)
        assert repo.get("42") is d

    def test_debate_with_complex_state(self, repo: DebateRepository) -> None:
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
                pro_argument=Argument(role=AgentRole.PRO, content=f"Pro point {i}"),
                con_argument=Argument(role=AgentRole.CON, content=f"Con point {i}"),
            )
            debate.add_round(r)

        debate.set_verdict(
            Verdict(summary="Final summary", recommendation="Final rec.")
        )

        repo.save(debate)
        retrieved = repo.get("complex-1")
        assert retrieved is debate
        assert retrieved.topic == "Complex debate?"
        assert retrieved.status == DebateStatus.COMPLETED
        assert len(retrieved.rounds) == 3
        assert retrieved.verdict is not None
        assert retrieved.verdict.summary == "Final summary"
        assert retrieved.verdict.recommendation == "Final rec."
        assert retrieved.rounds[1].pro_argument is not None
        assert retrieved.rounds[1].pro_argument.content == "Pro point 2"

    def test_delete_after_save_same_reference(
        self, repo: DebateRepository, sample_debate: Debate
    ) -> None:
        repo.save(sample_debate)
        repo.delete(sample_debate.id)
        # Re-saving the same object instance should make it retrievable
        repo.save(sample_debate)
        assert repo.get(sample_debate.id) is sample_debate

    def test_list_reflects_multiple_operations(self, repo: DebateRepository) -> None:
        d1 = Debate(id="d1", topic="T1")
        d2 = Debate(id="d2", topic="T2")
        d3 = Debate(id="d3", topic="T3")

        repo.save(d1)
        repo.save(d2)
        repo.save(d3)
        assert len(repo.list()) == 3

        repo.delete("d2")
        assert len(repo.list()) == 2
        assert repo.list() == [d1, d3]

        repo.save(Debate(id="d4", topic="T4"))
        assert len(repo.list()) == 3
        assert [d.id for d in repo.list()] == ["d1", "d3", "d4"]

    def test_repository_state_is_isolated(self, repo: DebateRepository) -> None:
        """Each repository instance has its own state."""
        repo2 = InMemoryDebateRepository()
        repo.save(Debate(id="a", topic="Repo 1"))
        repo2.save(Debate(id="b", topic="Repo 2"))
        assert len(repo.list()) == 1
        assert len(repo2.list()) == 1
        assert repo.get("a") is not None
        assert repo2.get("a") is None
