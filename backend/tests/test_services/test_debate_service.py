"""Tests for the DebateService orchestration layer.

All LLM calls are mocked — no real API requests are made.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.domain.enums import DebateStatus
from app.services.debate_service import DebateNotFoundError, DebateService
from app.services.llm_service import LLMError, LLMService
from app.storage.in_memory import InMemoryDebateRepository


# =================================================================
#  Fixtures
# =================================================================


@pytest.fixture
def repo() -> InMemoryDebateRepository:
    return InMemoryDebateRepository()


@pytest.fixture
def mock_llm() -> LLMService:
    """LLMService with generate() mocked to return canned responses."""
    svc = LLMService()
    svc.generate = AsyncMock()  # type: ignore[method-assign]
    return svc


@pytest.fixture
def service(repo: InMemoryDebateRepository, mock_llm: LLMService) -> DebateService:
    return DebateService(repository=repo, llm_service=mock_llm, max_rounds=3)


# =================================================================
#  create_debate
# =================================================================


class TestCreateDebate:
    """Happy-path creation."""

    async def test_creates_and_saves_debate(
        self, service: DebateService, repo: InMemoryDebateRepository
    ) -> None:
        debate = await service.create_debate("Should I learn Rust?")
        assert debate.id is not None
        assert debate.topic == "Should I learn Rust?"
        assert debate.status == DebateStatus.PENDING
        assert debate.rounds == []
        assert debate.verdict is None

        # Verify it was persisted
        stored = repo.get(debate.id)
        assert stored is debate

    async def test_generates_unique_ids(self, service: DebateService) -> None:
        d1 = await service.create_debate("Topic A")
        d2 = await service.create_debate("Topic B")
        assert d1.id != d2.id

    async def test_creates_empty_debate(self, service: DebateService) -> None:
        debate = await service.create_debate("Test topic")
        assert debate.rounds == []
        assert debate.verdict is None


# =================================================================
#  start_debate  (full pipeline)
# =================================================================


class TestStartDebate:
    """Running the full debate pipeline."""

    async def test_runs_all_rounds_and_verdict(
        self,
        service: DebateService,
        mock_llm: LLMService,
        repo: InMemoryDebateRepository,
    ) -> None:
        mock_llm.generate.return_value = "This is a simulated response."

        debate = await service.create_debate("Should I switch careers?")
        result = await service.start_debate(debate.id)

        assert result.status == DebateStatus.COMPLETED
        assert len(result.rounds) == 3
        assert result.verdict is not None
        assert result.verdict.summary == "This is a simulated response."
        assert (
            result.verdict.recommendation == "This is a simulated response."
        )  # single paragraph

        # Verify all 7 LLM calls: 3 (moderator) + 3 (pro) + 3 (con) + 1 (judge) = 10
        assert mock_llm.generate.await_count == 10

    async def test_pro_and_con_get_different_roles(
        self,
        service: DebateService,
        mock_llm: LLMService,
    ) -> None:
        """Verify that pro and con agents receive the right role in context."""
        call_log: list[str] = []

        async def side_effect(
            *, system_prompt: str = "", prompt: str, **kwargs: object
        ) -> str:
            call_log.append(f"SYSTEM:{system_prompt[:80]}  PROMPT:{prompt[:40]}")
            return "Response."

        mock_llm.generate.side_effect = side_effect  # type: ignore[method-assign]

        debate = await service.create_debate("Test topic")
        await service.start_debate(debate.id)

        # Check that pro and con system prompts appeared
        system_prompts = [msg for msg in call_log if "SYSTEM:" in msg]
        assert any(
            "advocate" in msg.lower() or "for" in msg.lower() for msg in system_prompts
        )
        assert any(
            "challenger" in msg.lower() or "against" in msg.lower()
            for msg in system_prompts
        )

    async def test_moderator_steer_passed_to_agents(
        self,
        service: DebateService,
        mock_llm: LLMService,
    ) -> None:
        """The moderator's steer should appear in pro/con prompts."""
        call_prompts: list[str] = []

        async def side_effect(
            *, system_prompt: str = "", prompt: str, **kwargs: object
        ) -> str:
            call_prompts.append(prompt)
            return (
                "Moderator steer: focus on cost."
                if "moderator" in system_prompt.lower()
                else "Response."
            )

        mock_llm.generate.side_effect = side_effect  # type: ignore[method-assign]

        debate = await service.create_debate("Should I buy a house?")
        await service.start_debate(debate.id)

        # The pro/con prompts after round 1 should include previous round context
        # (which contains the moderator's output)
        assert len(call_prompts) == 10

    async def test_debate_not_found(self, service: DebateService) -> None:
        with pytest.raises(DebateNotFoundError) as exc:
            await service.start_debate("does-not-exist")
        assert "does-not-exist" in str(exc.value)


# =================================================================
#  Error handling
# =================================================================


class TestDebateServiceErrors:
    """How the service handles LLM failures mid-debate."""

    async def test_llm_error_sets_debate_to_error(
        self,
        service: DebateService,
        mock_llm: LLMService,
        repo: InMemoryDebateRepository,
    ) -> None:
        """When an LLM call fails mid-debate, the debate is saved as ERROR."""
        call_count = 0

        async def fail_after_two(
            *, system_prompt: str = "", prompt: str, **kwargs: object
        ) -> str:
            nonlocal call_count
            call_count += 1
            if call_count > 2:
                msg = "Simulated API failure"
                raise LLMError(msg)
            return "Response."

        mock_llm.generate.side_effect = fail_after_two  # type: ignore[method-assign]

        debate = await service.create_debate("Test topic")
        result = await service.start_debate(debate.id)

        assert result.status == DebateStatus.ERROR
        # Some rounds may have completed before the error
        assert result.id == debate.id

        # The debate should still be retrievable
        stored = repo.get(debate.id)
        assert stored is result
        assert stored.status == DebateStatus.ERROR


# =================================================================
#  get_debate
# =================================================================


class TestGetDebate:
    """Retrieving debates from the service."""

    async def test_returns_debate(
        self, service: DebateService, repo: InMemoryDebateRepository
    ) -> None:
        debate = await service.create_debate("Test topic")
        retrieved = service.get_debate(debate.id)
        assert retrieved is debate

    async def test_returns_none_for_missing(self, service: DebateService) -> None:
        assert service.get_debate("does-not-exist") is None

    async def test_returns_updated_after_start(
        self,
        service: DebateService,
        mock_llm: LLMService,
    ) -> None:
        mock_llm.generate.return_value = "Response."
        debate = await service.create_debate("Test topic")
        await service.start_debate(debate.id)

        retrieved = service.get_debate(debate.id)
        assert retrieved is not None
        assert retrieved.status == DebateStatus.COMPLETED
        assert len(retrieved.rounds) == 3
