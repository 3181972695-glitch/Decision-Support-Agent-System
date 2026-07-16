"""Additional edge-case tests for DebateService."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from app.domain.debate import Debate
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
    svc.generate_stream = Mock(side_effect=NotImplementedError("Streaming not mocked"))
    return svc


@pytest.fixture
def service(repo: InMemoryDebateRepository, mock_llm: LLMService) -> DebateService:
    return DebateService(repository=repo, llm_service=mock_llm)


async def _run_full_debate(
    service: DebateService,
    debate_id: str,
) -> Debate:
    """Run a debate to completion, continuing through pauses."""
    import asyncio

    async def _keep_going() -> None:
        for _ in range(60):
            debate = await service.get_debate(debate_id)
            if debate is None or debate.is_completed():
                return
            if debate.awaiting_input:
                await service.continue_debate(debate_id)
            await asyncio.sleep(0.05)

    result, _ = await asyncio.gather(
        service.start_debate(debate_id),
        _keep_going(),
    )
    return result


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
        assert await service.get_debate(d1.id) is not None
        assert await service.get_debate(d2.id) is not None

    async def test_service_not_found_on_deleted_debate(
        self, service: DebateService, repo: InMemoryDebateRepository
    ) -> None:
        debate = await service.create_debate("Test topic")
        await repo.delete(debate.id)
        assert await service.get_debate(debate.id) is None

    async def test_start_debate_with_one_round(self, mock_llm: LLMService) -> None:
        """A 1-round debate completes without pausing."""
        svc = DebateService(
            repository=InMemoryDebateRepository(),
            llm_service=mock_llm,
        )
        mock_llm.generate.return_value = "Response."
        debate = await svc.create_debate("Test topic", max_rounds=1)
        result = await svc.start_debate(debate.id)
        assert result.status == DebateStatus.COMPLETED
        assert len(result.rounds) == 1
        assert result.verdict is not None

    async def test_start_multiple_times_raises_already_running(
        self, service: DebateService, mock_llm: LLMService
    ) -> None:
        mock_llm.generate.return_value = "Response."
        debate = await service.create_debate("Test topic")
        debate.max_rounds = 1
        await service._repo.save(debate)
        result1 = await service.start_debate(debate.id)
        assert result1.status == DebateStatus.COMPLETED

        # Starting again on a completed debate raises
        with pytest.raises(Exception) as exc:
            await service.start_debate(debate.id)
        assert "already running or completed" in str(exc.value).lower()

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
            # 10 calls for round 1, then fail on verdict (call 11)
            if call_count > 10:
                raise LLMError("Verdict failure")
            return "Response."

        mock_llm.generate.side_effect = side_effect

        debate = await service.create_debate("Test topic")
        debate.max_rounds = 1
        await service._repo.save(debate)
        result = await service.start_debate(debate.id)
        assert result.status == DebateStatus.ERROR
        # 1 round completed but verdict failed
        assert len(result.rounds) == 1

    async def test_save_debate_persists_updated_state(
        self, service: DebateService, repo: InMemoryDebateRepository
    ) -> None:
        debate = await service.create_debate("Test topic")

        # Simulate external verdict setting + saving via public API
        debate.advance_status(DebateStatus.COMPLETED)
        await service.save_debate(debate)
        stored = await service.get_debate(debate.id)
        assert stored is not None
        assert stored.id == debate.id
        assert stored.status == DebateStatus.COMPLETED

    async def test_three_round_debate(
        self, service: DebateService, mock_llm: LLMService
    ) -> None:
        """A full 3-round debate completes via continue."""
        mock_llm.generate.return_value = "Response."
        debate = await service.create_debate("Test topic", max_rounds=3)
        result = await _run_full_debate(service, debate.id)
        assert result.status == DebateStatus.COMPLETED
        assert len(result.rounds) == 3
        assert result.verdict is not None
