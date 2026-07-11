"""API routes for debate management."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from app.api.schemas import (
    ArgumentResponse,
    DebateCreate,
    DebateResponse,
    DebateStatusEnum,
    RoundResponse,
    VerdictResponse,
)
from app.domain.enums import DebateStatus
from app.services.debate_service import DebateService
from app.services.llm_service import LLMService
from app.storage.in_memory import InMemoryDebateRepository

logger = logging.getLogger("app.api.debates")

router = APIRouter(prefix="/debates", tags=["debates"])

# ── Background task tracking ────────────────────────────────────
# Keep a strong reference to background tasks so they don't get
# garbage-collected before they complete.
_background_tasks: set[asyncio.Task[None]] = set()


def _cleanup_done_task(task: asyncio.Task[None]) -> None:
    """Remove a finished background task from the tracking set."""
    _background_tasks.discard(task)


# ── Dependency wiring ───────────────────────────────────────────

_repo = InMemoryDebateRepository()
_llm = LLMService()
_debate_service = DebateService(repository=_repo, llm_service=_llm)


def get_debate_service() -> DebateService:
    """Dependency provider for DebateService (singleton)."""
    return _debate_service


# ── Response builders ───────────────────────────────────────────


def _argument_to_response(arg: object | None) -> ArgumentResponse | None:
    """Convert a domain Argument to a response schema."""
    if arg is None:
        return None
    role = getattr(arg, "role", "")
    content = getattr(arg, "content", "")
    created_at = getattr(arg, "created_at", None)
    return ArgumentResponse(
        role=role.value if hasattr(role, "value") else str(role),
        content=content,
        created_at=created_at,
    )


def _round_to_response(
    round_: object,
) -> RoundResponse:
    """Convert a domain Round to a response schema."""
    # Round is a dataclass, access fields directly
    return RoundResponse(
        round_number=getattr(round_, "round_number", 0),
        moderator_summary=getattr(round_, "moderator_summary", None),
        moderator_steer=getattr(round_, "moderator_steer", None),
        pro_argument=_argument_to_response(getattr(round_, "pro_argument", None)),
        con_argument=_argument_to_response(getattr(round_, "con_argument", None)),
    )


def _verdict_to_response(verdict: object | None) -> VerdictResponse | None:
    """Convert a domain Verdict to a response schema."""
    if verdict is None:
        return None
    return VerdictResponse(
        summary=getattr(verdict, "summary", ""),
        recommendation=getattr(verdict, "recommendation", ""),
        created_at=getattr(verdict, "created_at", None),
    )


def _debate_to_response(debate: object) -> DebateResponse:
    """Convert a domain Debate to a response schema."""
    rounds_list = getattr(debate, "rounds", [])
    return DebateResponse(
        id=getattr(debate, "id", ""),
        topic=getattr(debate, "topic", ""),
        status=DebateStatusEnum(getattr(debate, "status", "pending").value),
        rounds=[_round_to_response(r) for r in rounds_list],
        verdict=_verdict_to_response(getattr(debate, "verdict", None)),
        created_at=getattr(debate, "created_at", datetime.now()),
        updated_at=getattr(debate, "updated_at", None),
    )


# ── Routes ──────────────────────────────────────────────────────


@router.post("/", response_model=DebateResponse, status_code=201)
async def create_debate(
    payload: DebateCreate,
    service: DebateService = Depends(get_debate_service),
):
    """Create a new debate for the given topic."""
    debate = await service.create_debate(payload.topic)
    logger.info("Created debate %s: topic=%r", debate.id, payload.topic[:60])
    return _debate_to_response(debate)


@router.get("/{debate_id}", response_model=DebateResponse)
async def get_debate(
    debate_id: str,
    service: DebateService = Depends(get_debate_service),
):
    """Retrieve the current state of a debate."""
    debate = service.get_debate(debate_id)
    if debate is None:
        raise HTTPException(
            status_code=404,
            detail=f"Debate '{debate_id}' not found",
        )
    return _debate_to_response(debate)


@router.post("/{debate_id}/start", response_model=DebateResponse)
async def start_debate(
    debate_id: str,
    service: DebateService = Depends(get_debate_service),
):
    """Start the debate pipeline in the background and return immediately.

    The debate is advanced to IN_PROGRESS, then the full pipeline
    (moderator → pro → con for each round, then verdict) runs as a
    background asyncio task. The frontend polls GET /debates/{id}
    to observe progress as rounds complete.
    """
    debate = service.get_debate(debate_id)
    if debate is None:
        raise HTTPException(
            status_code=404,
            detail=f"Debate '{debate_id}' not found",
        )

    # Advance to IN_PROGRESS so the frontend sees the transition immediately.
    debate.advance_status(DebateStatus.IN_PROGRESS)
    service.save_debate(debate)

    # Kick off the slow pipeline in the background.
    task = asyncio.create_task(service.start_debate(debate_id))
    _background_tasks.add(task)
    task.add_done_callback(_cleanup_done_task)

    return _debate_to_response(debate)


@router.get("/{debate_id}/rounds/{round_number}", response_model=RoundResponse)
async def get_round(
    debate_id: str,
    round_number: int,
    service: DebateService = Depends(get_debate_service),
):
    """Retrieve a specific round of a debate."""
    debate = service.get_debate(debate_id)
    if debate is None:
        raise HTTPException(
            status_code=404,
            detail=f"Debate '{debate_id}' not found",
        )

    for r in debate.rounds:
        if r.round_number == round_number:
            return _round_to_response(r)

    raise HTTPException(
        status_code=404,
        detail=f"Round {round_number} not found in debate '{debate_id}'",
    )
