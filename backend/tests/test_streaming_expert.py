"""Tests for StreamingExpertDebateService."""

import json
from unittest.mock import AsyncMock

import pytest

from app.services.streaming_expert_service import StreamingExpertDebateService
from app.services.llm_service import LLMService


async def _collect(service: StreamingExpertDebateService, mode: str, question: str) -> list[dict]:
    """Collect all SSE events from a streaming debate."""
    events: list[dict] = []
    async for event_str in service.stream_debate(mode, question):
        # Parse SSE format: "event: type\ndata: {json}\n\n"
        lines = event_str.strip().split("\n")
        event_type = ""
        event_data = {}
        for line in lines:
            if line.startswith("event:"):
                event_type = line[6:].strip()
            elif line.startswith("data:"):
                event_data = json.loads(line[5:].strip())
        events.append({"event": event_type, "data": event_data})
    return events


_SAMPLE_GENERATED = [
    {"role": "AI Strategy Consultant", "expertise": "AI strategy",
     "system_prompt": "You analyze AI strategy."},
    {"role": "Security Engineer", "expertise": "Security",
     "system_prompt": "You analyze security."},
    {"role": "Engineering Manager", "expertise": "Productivity",
     "system_prompt": "You analyze productivity."},
]


class _MockStream:
    """Helper to create an async generator mock for generate_stream."""
    def __init__(self, tokens: list[str]):
        self.tokens = tokens

    async def __call__(self, *args, **kwargs):
        for token in self.tokens:
            yield token


@pytest.fixture
def mock_llm() -> LLMService:
    svc = LLMService()
    tokens = ["Analysis ", "from ", "expert. ", "More ", "text. ", "\nARGUMENTS:a|b|c"]
    svc.generate_stream = _MockStream(tokens)  # type: ignore[method-assign]
    svc.generate = AsyncMock(return_value="Mock.")
    return svc


@pytest.fixture
def mock_generator():
    gen = AsyncMock()
    gen.generate.return_value = _SAMPLE_GENERATED
    return gen


@pytest.fixture
def service(mock_llm: LLMService, mock_generator) -> StreamingExpertDebateService:
    return StreamingExpertDebateService(
        llm_service=mock_llm, expert_generator=mock_generator,
    )


@pytest.mark.asyncio
async def test_unknown_mode_returns_error(service: StreamingExpertDebateService) -> None:
    """Unknown mode should yield an error event, not crash."""
    events = await _collect(service, "nonexistent", "test question")
    assert any(e["event"] == "error" for e in events)


@pytest.mark.asyncio
async def test_stream_emits_phase_events(service: StreamingExpertDebateService) -> None:
    """Should emit phase events for analysis, debate, judge, complete."""
    events = await _collect(service, "software", "Test question?")
    phases = [e["data"]["status"] for e in events if e["event"] == "phase"]
    assert "analysis" in phases
    assert "debate" in phases
    assert "judge" in phases
    assert "complete" in phases


@pytest.mark.asyncio
async def test_stream_emits_expert_chunks(service: StreamingExpertDebateService) -> None:
    """Should emit analysis_chunk events for each expert."""
    events = await _collect(service, "software", "Test question?")
    chunks = [e for e in events if e["event"] == "analysis_chunk"]
    assert len(chunks) > 0
    # Should mention all 3 experts' roles
    roles_in_chunks = {e["data"]["role"] for e in chunks if "role" in e["data"]}
    assert "Architect" in roles_in_chunks
    assert "Security Engineer" in roles_in_chunks
    assert "Performance Engineer" in roles_in_chunks


@pytest.mark.asyncio
async def test_stream_emits_debate_events(service: StreamingExpertDebateService) -> None:
    """Should emit debate_start and debate_done for each pair."""
    events = await _collect(service, "software", "Test question?")
    starts = [e for e in events if e["event"] == "debate_start"]
    dones = [e for e in events if e["event"] == "debate_done"]
    # 3 experts × 2 others = 6 debate pairs
    assert len(starts) == 6
    assert len(dones) == 6


@pytest.mark.asyncio
async def test_stream_emits_judge_events(service: StreamingExpertDebateService) -> None:
    """Should emit judge_start, judge_chunk, and judge_done."""
    events = await _collect(service, "software", "Test question?")
    starts = [e for e in events if e["event"] == "judge_start"]
    chunks = [e for e in events if e["event"] == "judge_chunk"]
    dones = [e for e in events if e["event"] == "judge_done"]
    assert len(starts) >= 1
    assert len(chunks) > 0
    assert len(dones) == 1
    # judge_done should have confidence and final_decision
    assert "confidence" in dones[0]["data"]
    assert "final_decision" in dones[0]["data"]


@pytest.mark.asyncio
async def test_stream_emits_result_event(service: StreamingExpertDebateService) -> None:
    """Should emit a final result event with full structure."""
    events = await _collect(service, "software", "Test question?")
    results = [e for e in events if e["event"] == "result"]
    assert len(results) == 1
    r = results[0]["data"]
    assert "mode" in r
    assert "experts" in r
    assert "debate_rounds" in r
    assert "final_decision" in r
    assert "confidence" in r
    assert len(r["experts"]) == 3
    assert len(r["debate_rounds"]) == 6


@pytest.mark.asyncio
async def test_dynamic_mode_emits_expert_generation(
    mock_llm, mock_generator,
) -> None:
    """Dynamic mode should emit expert_generation events."""
    svc = StreamingExpertDebateService(llm_service=mock_llm, expert_generator=mock_generator)
    events = await _collect(svc, "dynamic", "Should we adopt AI?")
    gen_events = [e for e in events if e["event"] == "expert_generated"]
    assert len(gen_events) == 3
    assert gen_events[0]["data"]["role"] == "AI Strategy Consultant"


@pytest.mark.asyncio
async def test_stream_event_order_is_correct(service: StreamingExpertDebateService) -> None:
    """Events should appear in the correct phase order."""
    events = await _collect(service, "software", "Test question?")
    # Collect event types in order
    event_types = [e["event"] for e in events]

    # First analysis phase events should appear after phase(analysis)
    analysis_start_idx = event_types.index("phase")
    # Should find expert_start events
    assert "expert_start" in event_types
    assert "analysis_chunk" in event_types
    assert "expert_done" in event_types

    # Debate events should appear
    assert "debate_start" in event_types

    # Judge events should appear near the end
    assert "judge_start" in event_types

    # Result should be the last meaningful event
    assert "result" in event_types
    # result should appear after judge_done
    judge_done_idx = event_types.index("judge_done")
    result_idx = event_types.index("result")
    assert result_idx > judge_done_idx
