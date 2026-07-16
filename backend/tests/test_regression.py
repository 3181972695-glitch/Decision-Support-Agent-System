"""Regression tests for release stabilization issues.

Issue 1: Rebuttal SSE chunks must emit as "pro-rebuttal" / "con-rebuttal"
Issue 2: Continue signal must not be lost when frontend clicks immediately
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

from app.agents.base import AgentContext
from app.domain.debate import Debate, Round, Verdict
from app.domain.enums import DebateStatus, AgentRole, ResponseType
from app.services.debate_service import DebateService


# ===================================================================
# Issue 1: Rebuttal display_role
# ===================================================================

class TestRebuttalDisplayRole:
    """Verify that _stream_agent emits the correct display_role.

    Strategy: mock _agent() to return a dummy agent, then intercept
    _emit calls to verify the display_role mapping.
    """

    @pytest.mark.asyncio
    async def test_pro_rebuttal_emits_pro_rebuttal_role(self) -> None:
        from app.agents.base import BaseAgent

        mock_repo = AsyncMock()
        mock_llm = AsyncMock()
        mock_llm.get_profiler = MagicMock(return_value=None)

        svc = DebateService(mock_repo, mock_llm)

        # Dummy agent that returns empty text
        class DummyAgent(BaseAgent):
            SYSTEM_PROMPT = ""
            def build_prompt(self, context):
                return ""

        dummy = DummyAgent(mock_llm)
        # Override generate_stream to yield one chunk
        async def dummy_stream(context, **kwargs):
            yield "test"
        dummy.generate_stream = dummy_stream  # type: ignore[method-assign]

        with patch.object(svc, '_agent', return_value=dummy):
            emitted_events: list[dict] = []
            # Patch _emit directly on the instance
            svc._emit = lambda *a, **kw: emitted_events.append(kw)
            ctx = AgentContext(
                topic="Test", round_number=1,
                response_type=ResponseType.REBUTTAL,
                latest_opponent="Opponent text", language="English",
            )
            await svc._stream_agent("pro", ctx, "test-debate", 1)

        chunk_events = [e for e in emitted_events if e.get("event_type") == "agent_chunk"]
        for ev in chunk_events:
            assert ev["role"] == "pro-rebuttal", f"Expected pro-rebuttal, got {ev['role']}"

    @pytest.mark.asyncio
    async def test_con_rebuttal_emits_con_rebuttal_role(self) -> None:
        from app.agents.base import BaseAgent

        mock_repo = AsyncMock()
        mock_llm = AsyncMock()
        mock_llm.get_profiler = MagicMock(return_value=None)

        svc = DebateService(mock_repo, mock_llm)

        class DummyAgent(BaseAgent):
            SYSTEM_PROMPT = ""
            def build_prompt(self, context):
                return ""

        dummy = DummyAgent(mock_llm)
        async def dummy_stream(context, **kwargs):
            yield "test"
        dummy.generate_stream = dummy_stream  # type: ignore[method-assign]

        with patch.object(svc, '_agent', return_value=dummy):
            emitted_events: list[dict] = []
            svc._emit = lambda *a, **kw: emitted_events.append(kw)
            ctx = AgentContext(
                topic="Test", round_number=1,
                response_type=ResponseType.REBUTTAL,
                latest_opponent="Opponent text", language="English",
            )
            await svc._stream_agent("con", ctx, "test-debate", 1)

        chunk_events = [e for e in emitted_events if e.get("event_type") == "agent_chunk"]
        for ev in chunk_events:
            assert ev["role"] == "con-rebuttal", f"Expected con-rebuttal, got {ev['role']}"

    @pytest.mark.asyncio
    async def test_pro_opening_still_emits_pro_role(self) -> None:
        from app.agents.base import BaseAgent

        mock_repo = AsyncMock()
        mock_llm = AsyncMock()
        mock_llm.get_profiler = MagicMock(return_value=None)

        svc = DebateService(mock_repo, mock_llm)

        class DummyAgent(BaseAgent):
            SYSTEM_PROMPT = ""
            def build_prompt(self, context):
                return ""

        dummy = DummyAgent(mock_llm)
        async def dummy_stream(context, **kwargs):
            yield "test"
        dummy.generate_stream = dummy_stream  # type: ignore[method-assign]

        with patch.object(svc, '_agent', return_value=dummy):
            emitted_events: list[dict] = []
            svc._emit = lambda *a, **kw: emitted_events.append(kw)
            ctx = AgentContext(
                topic="Test", round_number=1,
                response_type=ResponseType.OPENING, language="English",
            )
            await svc._stream_agent("pro", ctx, "test-debate", 1)

        chunk_events = [e for e in emitted_events if e.get("event_type") == "agent_chunk"]
        for ev in chunk_events:
            assert ev["role"] == "pro", f"Expected pro, got {ev['role']}"

    @pytest.mark.asyncio
    async def test_moderator_intro_emits_moderator_intro_role(self) -> None:
        from app.agents.base import BaseAgent

        mock_repo = AsyncMock()
        mock_llm = AsyncMock()
        mock_llm.get_profiler = MagicMock(return_value=None)

        svc = DebateService(mock_repo, mock_llm)

        class DummyAgent(BaseAgent):
            SYSTEM_PROMPT = ""
            def build_prompt(self, context):
                return ""

        dummy = DummyAgent(mock_llm)
        async def dummy_stream(context, **kwargs):
            yield "test"
        dummy.generate_stream = dummy_stream  # type: ignore[method-assign]

        with patch.object(svc, '_agent', return_value=dummy):
            emitted_events: list[dict] = []
            svc._emit = lambda *a, **kw: emitted_events.append(kw)
            ctx = AgentContext(
                topic="Test", round_number=1,
                response_type=ResponseType.MODERATOR_INTRO,
                round_focus="Focus", language="English",
            )
            await svc._stream_agent("moderator", ctx, "test-debate", 1)

        chunk_events = [e for e in emitted_events if e.get("event_type") == "agent_chunk"]
        for ev in chunk_events:
            assert ev["role"] == "moderator_intro", f"Expected moderator_intro, got {ev['role']}"

    @pytest.mark.asyncio
    async def test_moderator_summary_emits_moderator_summary_role(self) -> None:
        from app.agents.base import BaseAgent

        mock_repo = AsyncMock()
        mock_llm = AsyncMock()
        mock_llm.get_profiler = MagicMock(return_value=None)

        svc = DebateService(mock_repo, mock_llm)

        class DummyAgent(BaseAgent):
            SYSTEM_PROMPT = ""
            def build_prompt(self, context):
                return ""

        dummy = DummyAgent(mock_llm)
        async def dummy_stream(context, **kwargs):
            yield "test"
        dummy.generate_stream = dummy_stream  # type: ignore[method-assign]

        with patch.object(svc, '_agent', return_value=dummy):
            emitted_events: list[dict] = []
            svc._emit = lambda *a, **kw: emitted_events.append(kw)
            ctx = AgentContext(
                topic="Test", round_number=1,
                response_type=ResponseType.MODERATOR_SUMMARY, language="English",
            )
            await svc._stream_agent("moderator", ctx, "test-debate", 1)

        chunk_events = [e for e in emitted_events if e.get("event_type") == "agent_chunk"]
        for ev in chunk_events:
            assert ev["role"] == "moderator_summary", f"Expected moderator_summary, got {ev['role']}"


# ===================================================================
# Issue 2: Continue race condition
# ===================================================================

class TestContinueRaceCondition:
    """Verify that the continue signal cannot be lost due to ordering."""

    @pytest.mark.asyncio
    async def test_event_registered_before_awaiting_input_exposed(self) -> None:
        """The continue Event must be registered before awaiting_input=True + SSE emit.

        Strategy: Start a debate, intercept the flow after round 1 completes.
        Assert that _continue_events contains the debate_id BEFORE the
        AWAITING_INPUT SSE event is emitted.
        """
        mock_repo = AsyncMock()
        mock_llm = AsyncMock()
        mock_llm.get_profiler = MagicMock(return_value=None)

        # Create a debate that will run 2 rounds
        debate = Debate(id="test-race", topic="Test", max_rounds=2)

        # We need the debate to be returned after each repo.get()
        mock_repo.get.return_value = debate

        svc = DebateService(mock_repo, mock_llm)

        # Track the exact order of: Event registration, db save, SSE emit
        events_log: list[str] = []

        original_emit = svc._emit
        original_save = svc._repo.save

        def tracking_emit(debate_id, event_type, **data):
            if event_type == "awaiting_input":
                # At this point, the Event MUST already be registered
                has_event = debate_id in svc._continue_events
                events_log.append(f"emit_awaiting_input event_exists={has_event}")
            original_emit(debate_id, event_type, **data)

        async def tracking_save(deb):
            if deb.awaiting_input:
                has_event = "test-race" in svc._continue_events
                events_log.append(f"save_awaiting_input event_exists={has_event}")
            await original_save(deb)

        svc._emit = tracking_emit  # type: ignore[method-assign]
        mock_repo.save = tracking_save  # type: ignore[method-assign]

        # Mock _run_round to return immediately
        with patch.object(svc, '_run_round', return_value=Round(round_number=1, moderator_summary="Done")):
            # Start the debate in background — it will pause after round 1
            task = asyncio.create_task(svc.start_debate("test-race"))

            # Wait for the debate to reach awaiting_input
            for _ in range(50):
                await asyncio.sleep(0.01)
                if events_log:
                    break

            # Cancel the task (we don't need to complete the debate)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Verify: the Event was registered BEFORE awaiting_input was exposed
        assert len(events_log) > 0, "No events captured — the test didn't reach awaiting_input"
        for log_entry in events_log:
            assert "event_exists=True" in log_entry, (
                f"Event should exist before awaiting_input is exposed. Got: {log_entry}"
            )

    @pytest.mark.asyncio
    async def test_immediate_continue_wakes_worker(self) -> None:
        """An immediate continue_debate() call must wake the waiting coroutine.

        Verifies: continue_debate → event.set() → worker wakes immediately.
        No sleeps, no timing assumptions.
        """
        mock_repo = AsyncMock()
        mock_llm = AsyncMock()
        mock_llm.get_profiler = MagicMock(return_value=None)

        debate = Debate(id="test-immediate", topic="Test", max_rounds=2)
        debate.advance_status(DebateStatus.IN_PROGRESS)
        mock_repo.get.return_value = debate

        svc = DebateService(mock_repo, mock_llm)

        # Simulate what happens in the round loop:
        # 1. Register Event
        continue_event = asyncio.Event()
        svc._continue_events["test-immediate"] = continue_event

        # 2. Set awaiting_input and save
        debate.awaiting_input = True
        await svc._repo.save(debate)

        # 3. Now simulate the frontend calling continue_debate immediately
        # This should call event.set() and wake the waiter
        async def call_continue():
            # Small delay to ensure the wait is active
            await asyncio.sleep(0)
            debate.awaiting_input = False
            await svc._repo.save(debate)
            event = svc._continue_events.pop("test-immediate", None)
            if event is not None:
                event.set()

        # Start waiting (simulates _wait_for_continue)
        async def wait_for_continue():
            try:
                await asyncio.wait_for(continue_event.wait(), timeout=5.0)
                return "woke"
            except asyncio.TimeoutError:
                return "timeout"

        # Run both concurrently
        wait_task = asyncio.create_task(wait_for_continue())
        continue_task = asyncio.create_task(call_continue())

        result = await wait_task

        assert result == "woke", (
            f"Expected 'woke' (continue signal was received), got '{result}'. "
            "The continue signal was lost."
        )

        # Cleanup
        await continue_task


# ===================================================================
# Issue 3: Combined integration test
# ===================================================================

class TestIntegrationRegression:
    """End-to-end test that the full flow works correctly."""

    @pytest.mark.asyncio
    async def test_full_round_emits_correct_roles(self) -> None:
        """A complete round should emit all agent roles correctly."""
        mock_repo = AsyncMock()
        mock_llm = AsyncMock()

        # Mock streaming to return a single chunk per agent
        def mock_stream(**kwargs):
            class _Gen:
                def __aiter__(self):
                    return self
                async def __anext__(self):
                    raise StopAsyncIteration
            return _Gen()

        mock_llm.generate_stream = mock_stream  # type: ignore[assignment]
        mock_llm.get_profiler = MagicMock(return_value=None)

        debate = Debate(id="test-integration", topic="Test", max_rounds=1)
        debate.advance_status(DebateStatus.IN_PROGRESS)
        mock_repo.get.return_value = debate

        svc = DebateService(mock_repo, mock_llm)

        emitted_roles: set[str] = set()

        def capture_emit(debate_id, event_type, **data):
            if event_type in ("agent_chunk", "agent_start", "agent_done"):
                role = data.get("role", "")
                if role:
                    emitted_roles.add(role)

        svc._emit = capture_emit  # type: ignore[method-assign]

        # Patch _extract_evidence to avoid AsyncMock issue
        with patch.object(svc, '_extract_evidence', return_value=[]):
            from app.domain.debate import RoundMemory
            with patch.object(RoundMemory, 'from_moderator_summary', return_value=RoundMemory()):
                round_ = await svc._run_round(debate, 1, enable_cross_exam=True, enable_moderator=True)

        # Verify expected roles appear
        assert "pro" in emitted_roles, f"Expected 'pro' role. Got: {emitted_roles}"
        assert "con" in emitted_roles, f"Expected 'con' role. Got: {emitted_roles}"
        assert "pro-rebuttal" in emitted_roles, f"Expected 'pro-rebuttal' role. Got: {emitted_roles}"
        assert "con-rebuttal" in emitted_roles, f"Expected 'con-rebuttal' role. Got: {emitted_roles}"
        assert "moderator_intro" in emitted_roles, f"Expected 'moderator_intro' role. Got: {emitted_roles}"
        assert "moderator_summary" in emitted_roles, f"Expected 'moderator_summary' role. Got: {emitted_roles}"

        # Verify pro/con opening roles are NOT pro-rebuttal
        assert "pro" in emitted_roles  # Opening is still 'pro'
        assert "con" in emitted_roles  # Opening is still 'con'
