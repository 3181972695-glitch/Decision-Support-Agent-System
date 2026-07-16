"""SSE streaming endpoint for real-time debate progress.

Provides a GET endpoint that streams debate events to the client
using Server-Sent Events. The client connects via EventSource and
receives incremental updates as the debate runs.

Supports:
- Last-Event-ID for reconnection (resume from last seen event)
- Heartbeat every 15s to prevent proxy timeouts
- Proper headers for proxy compatibility
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.api.debates import get_debate_service
from app.services.debate_service import DebateService
from app.services.event_queue import (
    EventType,
    SSEEvent,
    get_event_queue_registry,
)

logger = logging.getLogger("app.api.sse")

router = APIRouter(prefix="/debates", tags=["sse"])

HEARTBEAT_INTERVAL = 15  # seconds


async def _sse_generator(
    debate_id: str,
    last_event_id: str | None,
    service: DebateService,
) -> "Any":
    """Generate SSE events for a debate, yielding formatted event strings.

    Creates a queue for the debate, reads events, and yields them.
    Sends a snapshot event first, then streams live events.
    Sends heartbeats to prevent proxy timeouts.
    """
    registry = get_event_queue_registry()
    queue = registry.create(debate_id)

    # Send the current state as a snapshot event so the client can
    # rebuild its view on reconnect.
    debate = await service.get_debate(debate_id)  # type: ignore[union-attr]
    if debate is not None:
        logger.info("[TRACE] >>> SSE snapshot debate=%s status=%s rounds=%d <<<", debate_id, debate.status.value, len(debate.rounds))
        snapshot = SSEEvent(
            event_type=EventType.DEBATE_STARTED,
            data={
                "topic": debate.topic,
                "max_rounds": debate.max_rounds,
                "status": debate.status.value,
                "rounds": len(debate.rounds),
                "awaiting_input": debate.awaiting_input,
                "updated_at": debate.updated_at.isoformat()
                if debate.updated_at
                else None,
            },
        )
        yield snapshot.to_sse()

    # If the debate is already complete, send a final event and close
    # without creating a new queue (the worker already finished).
    if debate is not None and debate.is_completed():
        logger.info("[TRACE] >>> SSE already_completed debate=%s <<<", debate_id)
        yield SSEEvent(
            event_type=EventType.DEBATE_COMPLETE,
            data={"message": "Debate completed"},
        ).to_sse()
        return

    heartbeat_task: asyncio.Task[None] | None = None

    async def _heartbeat() -> None:
        """Send periodic heartbeat events to keep the connection alive."""
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            try:
                queue.put_nowait(
                    SSEEvent(
                        event_type="heartbeat",
                        data={},
                    )
                )
            except asyncio.QueueFull:
                pass

    try:
        heartbeat_task = asyncio.create_task(_heartbeat())

        empty_reads = 0
        MAX_EMPTY_READS = 120  # 120 * 15s = 30 minutes max staleness

        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_INTERVAL)
                empty_reads = 0  # Reset on successful read
            except asyncio.TimeoutError:
                empty_reads += 1
                if empty_reads >= MAX_EMPTY_READS:
                    # No events for 30 minutes — check if debate is stalled
                    debate_check = await service.get_debate(debate_id)  # type: ignore[union-attr]
                    if debate_check is not None and debate_check.is_completed():
                        logger.warning("[SSE] debate=%s completed but no sentinel received, closing", debate_id)
                        yield SSEEvent(
                            event_type=EventType.DEBATE_COMPLETE,
                            data={"message": "Debate completed"},
                        ).to_sse()
                        break
                    elif debate_check is not None and debate_check.status.value == "error":
                        logger.warning("[SSE] debate=%s in error state, closing", debate_id)
                        yield SSEEvent(
                            event_type=EventType.DEBATE_ERROR,
                            data={"message": "Debate encountered an error"},
                        ).to_sse()
                        break
                    empty_reads = 0  # Reset — maybe the worker is just slow
                continue

            if event is None:
                # Sentinel: debate is complete, close the stream
                yield SSEEvent(
                    event_type=EventType.DEBATE_COMPLETE,
                    data={"message": "Debate completed"},
                ).to_sse()
                break

            yield event.to_sse()
    except asyncio.CancelledError:
        logger.debug("SSE client disconnected for debate %s", debate_id)
    finally:
        if heartbeat_task is not None:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
        # Don't remove the queue here — the debate service may still be pushing events


@router.get("/{debate_id}/stream")
async def debate_stream(
    debate_id: str,
    request: Request,
    service: DebateService = Depends(get_debate_service),
):
    """SSE endpoint for real-time debate streaming.

    Connect with EventSource to receive debate events as they happen.
    Reconnecting clients can send Last-Event-ID to resume from their
    last received event.
    """
    # Validate debate exists
    debate = await service.get_debate(debate_id)  # type: ignore[union-attr]
    if debate is None:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=404,
            detail=f"Debate '{debate_id}' not found",
        )

    last_event_id = request.headers.get("Last-Event-ID")

    logger.info(
        "[TRACE] >>> SSE GET /stream debate=%s last_event_id=%s <<<", debate_id, last_event_id
    )

    return StreamingResponse(
        _sse_generator(debate_id, last_event_id, service),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control, Last-Event-ID",
        },
    )
