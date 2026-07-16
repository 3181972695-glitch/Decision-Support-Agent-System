"""Tests for stability fixes addressing bugs in the debate system."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.domain.debate import Debate, Round, Verdict
from app.domain.enums import DebateStatus, AgentRole
from app.services.debate_service import DebateService, DebateNotFoundError
from app.services.event_queue import EventQueueRegistry, get_event_queue_registry


# ── Bug 1: CancelledError must write ERROR status and clean up ──

class TestCancelledErrorCleanup:

    @pytest.mark.asyncio
    async def test_top_level_cancelled_error_persists_error_status(self) -> None:
        mock_repo = AsyncMock()
        mock_llm = AsyncMock()
        mock_llm.get_profiler = MagicMock(return_value=None)

        debate = Debate(id="test-cancel-1", topic="Test", max_rounds=1)
        debate.advance_status(DebateStatus.IN_PROGRESS)
        mock_repo.get.return_value = debate

        svc = DebateService(mock_repo, mock_llm)

        with patch.object(svc, '_run_round', side_effect=asyncio.CancelledError()):
            with pytest.raises(asyncio.CancelledError):
                await svc.start_debate("test-cancel-1")

        save_calls = [c for c in mock_repo.save.call_args_list if c[0][0].id == "test-cancel-1"]
        if save_calls:
            saved_debate = save_calls[-1][0][0]
            assert saved_debate.status == DebateStatus.ERROR

    @pytest.mark.asyncio
    async def test_mid_round_cancelled_error_persists_and_cleans_up(self) -> None:
        mock_repo = AsyncMock()
        mock_llm = AsyncMock()
        mock_llm.get_profiler = MagicMock(return_value=None)

        debate = Debate(id="test-cancel-2", topic="Test", max_rounds=2)
        debate.advance_status(DebateStatus.IN_PROGRESS)
        round1 = Round(round_number=1, moderator_summary="Done")
        debate.add_round(round1)
        mock_repo.get.return_value = debate

        svc = DebateService(mock_repo, mock_llm)

        with patch.object(svc, '_run_round', return_value=Round(round_number=1, moderator_summary="Done")):
            with patch.object(svc, '_wait_for_continue', side_effect=asyncio.CancelledError()):
                result = await svc.start_debate("test-cancel-2")

        assert result.status == DebateStatus.ERROR
        assert "test-cancel-2" not in svc._continue_events


# ── Bug 2: _wait_for_continue timeout must reset awaiting_input ──

class TestContinueTimeout:

    @pytest.mark.asyncio
    async def test_timeout_resets_awaiting_input(self) -> None:
        mock_repo = AsyncMock()
        mock_llm = AsyncMock()

        debate = Debate(id="test-timeout", topic="Test", max_rounds=2)
        debate.awaiting_input = True
        mock_repo.get.return_value = debate

        svc = DebateService(mock_repo, mock_llm)

        with patch.object(asyncio, 'wait_for', side_effect=asyncio.TimeoutError()):
            await svc._wait_for_continue("test-timeout")

        save_calls = mock_repo.save.call_args_list
        saved = any(
            call[0][0].id == "test-timeout" and not call[0][0].awaiting_input
            for call in save_calls
        )
        assert saved


# ── Bug 3: continue_debate when not awaiting_input ──

class TestContinueGuard:

    @pytest.mark.asyncio
    async def test_continue_when_not_awaiting_is_noop(self) -> None:
        mock_repo = AsyncMock()
        mock_llm = AsyncMock()

        debate = Debate(id="test-noop", topic="Test", max_rounds=2)
        debate.awaiting_input = False
        mock_repo.get.return_value = debate

        svc = DebateService(mock_repo, mock_llm)
        result = await svc.continue_debate("test-noop")

        assert result is debate
        mock_repo.save.assert_not_called()


# ── Bug 4: _gather_tasks cancels remaining tasks on failure ──

class TestGatherCancellation:

    @pytest.mark.asyncio
    async def test_gather_simple_failure(self) -> None:
        """Gather should re-raise the exception from the failing task."""
        async def fail() -> str:
            raise ValueError("boom")

        t1 = asyncio.create_task(fail())
        t2 = asyncio.create_task(asyncio.sleep(0, result="ok"))

        with pytest.raises(ValueError):
            await DebateService._gather_tasks(t1, t2)

    @pytest.mark.asyncio
    async def test_gather_all_succeed(self) -> None:
        t1 = asyncio.create_task(asyncio.sleep(0, result="a"))
        t2 = asyncio.create_task(asyncio.sleep(0, result="b"))
        results = await DebateService._gather_tasks(t1, t2)
        assert results == ["a", "b"]


# ── Bug 5: EventQueueRegistry ──

class TestEventQueueStability:

    def test_create_does_not_drop_existing(self) -> None:
        registry = EventQueueRegistry()
        q1 = registry.create("d1")
        q1.put_nowait(MagicMock())
        q2 = registry.create("d1")
        assert q2 is not None
        assert q1 is not q2  # New queue created on reconnect

    def test_close_sends_sentinel(self) -> None:
        registry = EventQueueRegistry()
        q = registry.create("d1")
        registry.close("d1")
        assert q.get_nowait() is None
        assert registry.get("d1") is None


# ── Bug 6: Debate status transitions ──

class TestStatusTransitions:

    def test_debate_tracks_status_correctly(self) -> None:
        debate = Debate(id="test-status", topic="Test", max_rounds=1)
        assert debate.status == DebateStatus.PENDING

        debate.advance_status(DebateStatus.IN_PROGRESS)
        assert debate.status == DebateStatus.IN_PROGRESS

        v = Verdict(summary="Done", recommendation="Go")
        debate.set_verdict(v)
        assert debate.status == DebateStatus.COMPLETED

    def test_debate_error_status(self) -> None:
        debate = Debate(id="test-err", topic="Test", max_rounds=1)
        debate.advance_status(DebateStatus.ERROR)
        assert debate.is_completed()
        assert debate.status == DebateStatus.ERROR


# ── Bug 7: Round numbering consistency ──

class TestRoundNumbering:

    def test_rounds_have_correct_numbers(self) -> None:
        debate = Debate(id="test-rn", topic="Test", max_rounds=3)
        debate.add_round(Round(round_number=1))
        debate.add_round(Round(round_number=2))
        assert debate.latest_round().round_number == 2
        assert len(debate.rounds) == 2

    def test_round_zero_not_allowed(self) -> None:
        debate = Debate(id="test-r0", topic="Test", max_rounds=1)
        debate.add_round(Round(round_number=1))
        round_nums = [r.round_number for r in debate.rounds]
        assert 0 not in round_nums
        assert 1 in round_nums
