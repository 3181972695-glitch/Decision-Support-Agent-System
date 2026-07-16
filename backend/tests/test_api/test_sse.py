"""Tests for the SSE streaming endpoint."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, Mock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.debates import get_debate_service
from app.main import app
from app.services.debate_service import DebateService
from app.services.llm_service import LLMService
from app.storage.in_memory import InMemoryDebateRepository


@pytest.fixture
def mock_llm() -> LLMService:
    svc = LLMService()
    svc.generate = AsyncMock(return_value="Mocked LLM response.")
    svc.generate_stream = Mock(side_effect=NotImplementedError("Streaming not mocked"))
    return svc


@pytest.fixture
def test_service(mock_llm: LLMService) -> DebateService:
    repo = InMemoryDebateRepository()
    return DebateService(repository=repo, llm_service=mock_llm)


@pytest.fixture
def async_client(test_service: DebateService) -> AsyncClient:
    def _override() -> DebateService:
        return test_service

    app.dependency_overrides[get_debate_service] = _override
    transport = ASGITransport(app=app)
    yield AsyncClient(transport=transport, base_url="http://test")
    app.dependency_overrides.clear()


async def _create_and_run(client: AsyncClient) -> str:
    """Create, start, and wait for a 1-round debate to complete."""
    resp = await client.post("/api/debates/", json={"topic": "Test", "max_rounds": 1})
    debate_id = resp.json()["id"]
    await client.post(f"/api/debates/{debate_id}/start")
    for _ in range(50):
        r = await client.get(f"/api/debates/{debate_id}")
        if r.json()["status"] in ("completed", "error"):
            break
        await asyncio.sleep(0.1)
    return debate_id


def _parse_sse_event(raw: str) -> dict | None:
    data = None
    event_type = None
    for line in raw.split("\n"):
        if line.startswith("event: "):
            event_type = line[7:]
        elif line.startswith("data: "):
            try:
                data = json.loads(line[6:])
            except json.JSONDecodeError:
                data = {"raw": line[6:]}
    if data is None:
        return None
    return {"event": event_type, **data}


class TestSSEHeaders:
    """SSE endpoint returns correct headers on completed debates."""

    @pytest.mark.asyncio
    async def test_200_on_completed_debate(self, async_client: AsyncClient) -> None:
        debate_id = await _create_and_run(async_client)
        async with async_client.stream(
            "GET", f"/api/debates/{debate_id}/stream", timeout=2.0
        ) as sse:
            assert sse.status_code == 200

    @pytest.mark.asyncio
    async def test_content_type(self, async_client: AsyncClient) -> None:
        debate_id = await _create_and_run(async_client)
        async with async_client.stream(
            "GET", f"/api/debates/{debate_id}/stream", timeout=2.0
        ) as sse:
            assert sse.headers["content-type"].startswith("text/event-stream")

    @pytest.mark.asyncio
    async def test_cache_control(self, async_client: AsyncClient) -> None:
        debate_id = await _create_and_run(async_client)
        async with async_client.stream(
            "GET", f"/api/debates/{debate_id}/stream", timeout=2.0
        ) as sse:
            assert sse.headers["cache-control"] == "no-cache"

    @pytest.mark.asyncio
    async def test_x_accel_buffering(self, async_client: AsyncClient) -> None:
        debate_id = await _create_and_run(async_client)
        async with async_client.stream(
            "GET", f"/api/debates/{debate_id}/stream", timeout=2.0
        ) as sse:
            assert sse.headers["x-accel-buffering"] == "no"

    @pytest.mark.asyncio
    async def test_404_nonexistent(self, async_client: AsyncClient) -> None:
        async with async_client.stream(
            "GET", "/api/debates/nonexistent/stream", timeout=1.0
        ) as sse:
            assert sse.status_code == 404


class TestSSEEvents:
    """SSE event delivery on completed debates."""

    @pytest.mark.asyncio
    async def test_completed_debate_sends_snapshot_and_completion(
        self, async_client: AsyncClient
    ) -> None:
        debate_id = await _create_and_run(async_client)

        async with async_client.stream(
            "GET", f"/api/debates/{debate_id}/stream", timeout=3.0
        ) as sse:
            assert sse.status_code == 200
            buffer = ""
            events: list[dict] = []
            async for chunk in sse.aiter_text():
                buffer += chunk
                while "\n\n" in buffer:
                    event_str, buffer = buffer.split("\n\n", 1)
                    parsed = _parse_sse_event(event_str)
                    if parsed:
                        events.append(parsed)

            assert len(events) >= 2
            assert events[0]["event"] == "debate_started"
            assert events[-1]["event"] == "debate_complete"
