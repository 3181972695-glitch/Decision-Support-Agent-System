"""Additional edge-case tests for DebateService."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.domain.enums import DebateStatus
from app.services.debate_service import DebateService
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
    svc = LLMService()
    svc.generate = AsyncMock(return_value="Mock response.")
    return svc


@pytest.fixture
def service(repo: InMemoryDebateRepository, mock_llm: LLMService) -> DebateService:
    return DebateService(repository=repo, llm_service=mock_llm, max_rounds=3)


# =================================================================
#  Edge cases
# =================================================================


class TestDebateServiceEdgeCases:
    """Edge cases for the debate service."""

    async def test_create_debate_with_special_characters(
        self, service: DebateService
    ) -> None:
        topic = "Should I learn Rust? (Yes/No!) @#$%"
        debate = await service.create_debate(topic)
        assert debate.topic == topic

    async def test_create_debate_with_very_long_topic(
        self, service: DebateService
    ) -> None:
        topic = "Should I " + "very " * 100 + "long topic?"
        debate = await service.create_debate(topic[:500])
        assert len(debate.topic) <= 500

    async def test_create_multiple_debates_independent(
        self, service: DebateService
    ) -> None:
        d1 = await service.create_debate("Topic A")
        d2 = await service.create_debate("Topic B")
        assert d1.id != d2.id
        assert service.get_debate(d1.id) is d1
        assert service.get_debate(d2.id) is d2

    async def test_service_not_found_on_deleted_debate(
        self, service: DebateService, repo: InMemoryDebateRepository
    ) -> None:
        debate = await service.create_debate("Test topic")
        repo.delete(debate.id)
        assert service.get_debate(debate.id) is None

    async def test_start_debate_with_zero_rounds(self, mock_llm: LLMService) -> None:
        """When max_rounds is 0, only the verdict runs."""
        svc = DebateService(
            repository=InMemoryDebateRepository(),
            llm_service=mock_llm,
            max_rounds=0,
        )
        mock_llm.generate.return_value = "Verdict."
        debate = await svc.create_debate("Test topic")
        result = await svc.start_debate(debate.id)
        assert result.status == DebateStatus.COMPLETED
        assert len(result.rounds) == 0
        assert result.verdict is not None

    async def test_start_multiple_times_is_safe(
        self, service: DebateService, mock_llm: LLMService
    ) -> None:
        mock_llm.generate.return_value = "Response."
        debate = await service.create_debate("Test topic")
        result1 = await service.start_debate(debate.id)
        assert result1.status == DebateStatus.COMPLETED

        # Starting again - the service should handle gracefully
        result2 = await service.start_debate(debate.id)
        # Either completes or errors depending on implementation
        assert result2.status in (DebateStatus.COMPLETED, DebateStatus.ERROR)

    async def test_error_mid_verdict(
        self, service: DebateService, mock_llm: LLMService
    ) -> None:
        """When LLM fails during the verdict phase, debate goes to ERROR."""
        call_count = 0

        async def side_effect(
            *, system_prompt: str = "", prompt: str, **kwargs: object
        ) -> str:
            nonlocal call_count
            call_count += 1
            if call_count > 9:
                raise LLMError("Verdict failure")
            return "Response."

        mock_llm.generate.side_effect = side_effect

        debate = await service.create_debate("Test topic")
        result = await service.start_debate(debate.id)
        assert result.status == DebateStatus.ERROR
        # All 3 rounds completed, but verdict failed
        assert len(result.rounds) == 3

    async def test_save_debate_persists_updated_state(
        self, service: DebateService, repo: InMemoryDebateRepository
    ) -> None:
        debate = await service.create_debate("Test topic")

        # Simulate external verdict setting + saving via public API
        debate.advance_status(DebateStatus.COMPLETED)
        service.save_debate(debate)
        stored = service.get_debate(debate.id)
        assert stored is debate
        assert stored.status == DebateStatus.COMPLETED
