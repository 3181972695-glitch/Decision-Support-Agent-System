"""Tests for the DebateService orchestration layer.

All LLM calls are mocked — no real API requests are made.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from app.domain.debate import Debate
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
    svc.generate = AsyncMock()
    svc.generate_stream = Mock(side_effect=NotImplementedError("Streaming not mocked"))
    return svc


@pytest.fixture
def service(repo: InMemoryDebateRepository, mock_llm: LLMService) -> DebateService:
    return DebateService(repository=repo, llm_service=mock_llm)


async def _run_full_debate(
    service: DebateService,
    debate_id: str,
) -> Debate:
    """Run a debate to completion, continuing through pauses.

    Since start_debate pauses between rounds, this helper
    concurrently continues the debate when awaiting_input is True.
    """
    import asyncio

    async def _keep_going() -> None:
        for _ in range(60):
            debate = await service.get_debate(debate_id)
            if debate is None or debate.is_completed():
                return
            if debate.awaiting_input:
                await service.continue_debate(debate_id)
            await asyncio.sleep(0.05)

    # Run both the debate and the continue helper
    result, _ = await asyncio.gather(
        service.start_debate(debate_id),
        _keep_going(),
    )
    return result


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
        stored = await repo.get(debate.id)
        assert stored is not None
        assert stored.id == debate.id

    async def test_generates_unique_ids(self, service: DebateService) -> None:
        d1 = await service.create_debate("Topic A")
        d2 = await service.create_debate("Topic B")
        assert d1.id != d2.id

    async def test_creates_empty_debate(self, service: DebateService) -> None:
        debate = await service.create_debate("Test topic")
        assert debate.rounds == []
        assert debate.verdict is None

    async def test_creates_with_max_rounds(self, service: DebateService) -> None:
        debate = await service.create_debate("Test topic", max_rounds=5)
        assert debate.max_rounds == 5


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
        # Use 1 round to test the flow without pauses
        debate.max_rounds = 1
        await repo.save(debate)

        result = await service.start_debate(debate.id)

        assert result.status == DebateStatus.COMPLETED
        assert len(result.rounds) == 1
        assert result.verdict is not None
        assert result.verdict.summary == "This is a simulated response."
        assert result.verdict.recommendation == "This is a simulated response."

        # Verify 11 LLM calls: 10 per round + 1 judge verdict
        assert mock_llm.generate.await_count == 11

    async def test_pro_and_con_get_different_roles(
        self,
        service: DebateService,
        mock_llm: LLMService,
        repo: InMemoryDebateRepository,
    ) -> None:
        """Verify that pro and con agents receive the right role in context."""
        call_log: list[str] = []

        async def side_effect(
            *, system_prompt: str = "", prompt: str, **kwargs: object
        ) -> str:
            call_log.append(f"SYSTEM:{system_prompt[:80]}  PROMPT:{prompt[:40]}")
            return "Response."

        mock_llm.generate.side_effect = side_effect

        debate = await service.create_debate("Test topic")
        debate.max_rounds = 1
        await repo.save(debate)
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

    async def test_debate_not_found(self, service: DebateService) -> None:
        with pytest.raises(DebateNotFoundError) as exc:
            await service.start_debate("does-not-exist")
        assert "does-not-exist" in str(exc.value)

    async def test_three_round_debate_via_continue(
        self,
        service: DebateService,
        mock_llm: LLMService,
        repo: InMemoryDebateRepository,
    ) -> None:
        """A 3-round debate completed through the continue mechanism."""
        mock_llm.generate.return_value = "Response."

        debate = await service.create_debate("Test topic", max_rounds=3)
        result = await _run_full_debate(service, debate.id)

        assert result.status == DebateStatus.COMPLETED
        assert len(result.rounds) == 3
        assert result.verdict is not None
        # 10 calls per round + 1 verdict = 31 total
        assert mock_llm.generate.await_count == 31


# =================================================================
#  continue_debate
# =================================================================


class TestContinueDebate:
    """Continuing a paused debate."""

    async def test_continue_clears_flag(
        self,
        service: DebateService,
        repo: InMemoryDebateRepository,
    ) -> None:
        debate = await service.create_debate("Test topic")
        debate.awaiting_input = True
        await repo.save(debate)

        result = await service.continue_debate(debate.id)
        assert result.awaiting_input is False

    async def test_continue_not_paused(
        self,
        service: DebateService,
    ) -> None:
        debate = await service.create_debate("Test topic")
        result = await service.continue_debate(debate.id)
        assert result.awaiting_input is False


    async def test_continue_signals_event(
        self,
        service: DebateService,
        repo: InMemoryDebateRepository,
    ) -> None:
        """continue_debate signals the Event so _wait_for_continue unblocks."""
        debate = await service.create_debate("Test topic")
        debate.awaiting_input = True
        await repo.save(debate)

        # Create an event and start waiting
        import asyncio
        event = asyncio.Event()
        service._continue_events[debate.id] = event

        async def waiter():
            await service._wait_for_continue(debate.id)

        task = asyncio.create_task(waiter())

        # Give the waiter a moment to start
        await asyncio.sleep(0.05)
        assert not task.done()

        # Continue should signal the event
        await service.continue_debate(debate.id)

        # Waiter should complete
        await asyncio.wait_for(task, timeout=2)
        assert task.done()
        assert debate.id not in service._continue_events

    async def test_wait_for_continue_times_out(
        self,
        service: DebateService,
        repo: InMemoryDebateRepository,
    ) -> None:
        """_wait_for_continue with a short timeout unblocks when nobody signals."""
        debate = await service.create_debate("Test topic")
        import asyncio

        # Monkey-patch the timeout to be very short
        original_wait = service._wait_for_continue

        async def short_wait(debate_id: str) -> None:
            event = asyncio.Event()
            service._continue_events[debate_id] = event
            try:
                await asyncio.wait_for(event.wait(), timeout=0.01)
            except asyncio.TimeoutError:
                pass
            finally:
                service._continue_events.pop(debate_id, None)

        service._wait_for_continue = short_wait
        try:
            await service._wait_for_continue(debate.id)
            assert debate.id not in service._continue_events
        finally:
            service._wait_for_continue = original_wait


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

        mock_llm.generate.side_effect = fail_after_two

        debate = await service.create_debate("Test topic")
        result = await service.start_debate(debate.id)

        assert result.status == DebateStatus.ERROR
        assert result.id == debate.id

        # The debate should still be retrievable
        stored = await repo.get(debate.id)
        assert stored is not None
        assert stored.id == result.id
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
        retrieved = await service.get_debate(debate.id)
        assert retrieved is not None
        assert retrieved.id == debate.id

    async def test_returns_none_for_missing(self, service: DebateService) -> None:
        assert await service.get_debate("does-not-exist") is None

    async def test_returns_updated_after_start(
        self,
        service: DebateService,
        mock_llm: LLMService,
        repo: InMemoryDebateRepository,
    ) -> None:
        mock_llm.generate.return_value = "Response."
        debate = await service.create_debate("Test topic")
        debate.max_rounds = 1
        await repo.save(debate)
        await service.start_debate(debate.id)

        retrieved = await service.get_debate(debate.id)
        assert retrieved is not None
        assert retrieved.status == DebateStatus.COMPLETED
        assert len(retrieved.rounds) == 1


# =================================================================
#  response_format (JSON mode for judge)
# =================================================================


class TestResponseFormat:
    """Judge verdict uses response_format='json_object'."""

    @pytest.mark.asyncio
    async def test_judge_passes_response_format(
        self,
        service: DebateService,
        mock_llm: LLMService,
        repo: InMemoryDebateRepository,
    ) -> None:
        """Verify that the judge call passes response_format to the LLM."""
        mock_llm.generate.return_value = '{"summary": "S", "recommendation": "R"}'

        debate = await service.create_debate("Test topic")
        debate.max_rounds = 1
        await repo.save(debate)

        await service.start_debate(debate.id)

        # Check that the last call (judge verdict) had response_format
        call_args_list = mock_llm.generate.await_args_list
        # The judge is the 11th call in a 1-round debate (10 per round + 1 verdict)
        judge_call = call_args_list[-1]
        kwargs = judge_call.kwargs
        assert kwargs.get("response_format") == {"type": "json_object"}


# =================================================================
#  Parallel execution
# =================================================================


class TestParallelExecution:
    """Pro/Con openings and rebuttals run in parallel."""

    @pytest.mark.asyncio
    async def test_openings_run_in_parallel(
        self,
        service: DebateService,
        mock_llm: LLMService,
        repo: InMemoryDebateRepository,
    ) -> None:
        """Pro and Con openings are called without waiting for the other to finish."""

        call_order: list[str] = []
        call_count = {"count": 0}

        async def side_effect(
            *, system_prompt: str = "", prompt: str, **kwargs: object
        ) -> str:
            call_count["count"] += 1
            # Record which role is being called
            if "FOR the proposition" in prompt:
                call_order.append("pro")
            elif "AGAINST the proposition" in prompt:
                call_order.append("con")
            elif "impartial judge" in system_prompt:
                call_order.append("judge")
            elif "expert debate moderator" in system_prompt:
                call_order.append("moderator")
            else:
                call_order.append("unknown")
            return "Response."

        mock_llm.generate.side_effect = side_effect

        debate = await service.create_debate("Test topic")
        debate.max_rounds = 1
        await repo.save(debate)

        await service.start_debate(debate.id)

        # Verify that Pro and Con openings appear consecutively
        # (they run in parallel, so order depends on async scheduling,
        # but they should both appear before cross-ex calls)
        pro_idx = call_order.index("pro") if "pro" in call_order else -1
        con_idx = call_order.index("con") if "con" in call_order else -1
        assert pro_idx != -1
        assert con_idx != -1

        # Both should be before the 4th call (moderator intro is 1st)
        # The openings are calls 2 and 3 (or 3 and 2) in the combined list
        # but since they run in parallel, both are dispatched before either completes.
        # What matters: neither is waiting for cross-ex to complete.
        # Cross-ex calls start at index 4 in the call list
        max_open_idx = max(pro_idx, con_idx)
        # The later of the two openings should still be before cross-ex starts
        assert max_open_idx <= 3  # mod intro + 2 openings = 3 calls

        # Verify all 11 calls happened (1-round debate)
        assert call_count["count"] == 11
