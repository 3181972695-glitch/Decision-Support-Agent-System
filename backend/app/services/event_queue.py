"""SSE event queue system for debate streaming.

Each debate gets an asyncio.Queue that DebateService pushes events into.
The SSE endpoint reads from the queue and sends events to the client.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("app.services.event_queue")

# Global monotonically-increasing sequence number for all SSE events
_seq_counter = itertools.count(1)


def _next_seq() -> int:
    return next(_seq_counter)


class EventType:
    """SSE event type constants."""

    DEBATE_STARTED = "debate_started"
    DEBATE_COMPLETE = "debate_complete"
    DEBATE_ERROR = "debate_error"

    ROUND_START = "round_start"
    ROUND_DONE = "round_done"

    AGENT_START = "agent_start"
    AGENT_CHUNK = "agent_chunk"
    AGENT_DONE = "agent_done"

    AWAITING_INPUT = "awaiting_input"

    VERDICT_START = "verdict_start"
    VERDICT_CHUNK = "verdict_chunk"
    VERDICT_DONE = "verdict_done"


@dataclass
class SSEEvent:
    """A single SSE event to be sent to the client."""

    event_type: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_sse(self) -> str:
        """Serialize to SSE format: 'event: TYPE\\ndata: JSON\\n\\n'."""
        payload = {"type": self.event_type, "timestamp": self.timestamp, **self.data}
        return f"event: {self.event_type}\ndata: {json.dumps(payload)}\n\n"


class EventQueueRegistry:
    """Registry of asyncio.Queue instances keyed by debate ID.

    When a debate starts, a queue is created. The SSE endpoint attaches
    to it. When the debate is complete, the queue is closed and removed.

    If no queue exists for a debate (e.g., no SSE client connected),
    events are silently dropped — the debate still runs normally.
    """

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue[SSEEvent | None]] = {}

    def create(self, debate_id: str) -> asyncio.Queue[SSEEvent | None]:
        """Create and register a queue for the given debate. Overwrites any existing."""
        queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue()
        self._queues[debate_id] = queue
        logger.debug("Event queue created for debate %s", debate_id)
        return queue

    def get(self, debate_id: str) -> asyncio.Queue[SSEEvent | None] | None:
        """Return the queue for a debate, or None if not registered."""
        return self._queues.get(debate_id)

    def remove(self, debate_id: str) -> None:
        """Remove the queue for a debate."""
        self._queues.pop(debate_id, None)
        logger.debug("Event queue removed for debate %s", debate_id)

    def push(self, debate_id: str, event: SSEEvent) -> None:
        import logging
        _logger = logging.getLogger("app.services.event_queue")
        role = event.data.get("role", "")
        if role and (role.endswith("-question") or role.endswith("-answer")):
            content = event.data.get("content", "")
            _logger.info(
                "[XDIAG] SSE_QUEUE_PUSH type=%s role=%s round=%s content_len=%d content_preview=%r",
                event.event_type, role, event.data.get("round_number", ""),
                len(str(content)) if content else 0,
                str(content)[:80] if content else "",
            )
        """Push an event to the debate's queue. No-op if no queue exists."""
        queue = self._queues.get(debate_id)
        if queue is not None:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(
                    "[TRACE] SSE DROP queue_full debate=%s event=%s", debate_id, event.event_type
                )
        else:
            logger.debug("[TRACE] SSE DROP no_queue debate=%s event=%s", debate_id, event.event_type)

    def close(self, debate_id: str) -> None:
        """Send a sentinel (None) and remove the queue."""
        queue = self._queues.pop(debate_id, None)
        if queue is not None:
            try:
                queue.put_nowait(None)  # Sentinel to signal EOF
            except asyncio.QueueFull:
                pass


# Singleton instance
_event_queue_registry: EventQueueRegistry | None = None


def get_event_queue_registry() -> EventQueueRegistry:
    """Return the singleton EventQueueRegistry."""
    global _event_queue_registry
    if _event_queue_registry is None:
        _event_queue_registry = EventQueueRegistry()
    return _event_queue_registry
