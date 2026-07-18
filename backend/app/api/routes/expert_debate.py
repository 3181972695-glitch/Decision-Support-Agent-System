"""API routes for Expert Debate Mode."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.services.expert_debate_service import ExpertDebateService

logger = logging.getLogger("app.api.routes.expert_debate")

router = APIRouter(prefix="/expert", tags=["expert"])


# ── Schemas ──────────────────────────────────────────────────────


class ExpertDebateRequest(BaseModel):
    mode: str = Field(..., description="Expert mode key (e.g. 'software', 'career')")
    question: str = Field(..., min_length=1, max_length=2000, description="Question to debate")


class ExpertAnalysis(BaseModel):
    role: str
    analysis: str
    arguments: list[str] = []


class DebateRound(BaseModel):
    speaker: str
    response_to: str
    content: str


class ExpertDebateResponse(BaseModel):
    mode: str
    question: str
    experts: list[ExpertAnalysis]
    debate_rounds: list[DebateRound] = []
    final_decision: str
    confidence: int = 0
    confidence_reason: list[str] = []
    uncertainties: list[str] = []
    key_tradeoffs: list[str] = []


# ── Dependency ───────────────────────────────────────────────────


def get_expert_debate_service(request: Request) -> ExpertDebateService:
    return request.app.state.expert_debate_service  # type: ignore[no-any-return]


# ── Routes ───────────────────────────────────────────────────────


@router.post("/debate", response_model=ExpertDebateResponse)
async def expert_debate(
    payload: ExpertDebateRequest,
    service: ExpertDebateService = Depends(get_expert_debate_service),
):
    """Run a multi-expert debate with cross-critique and final decision."""
    logger.info(
        "[EXPERT_DEBATE] POST /expert/debate mode=%s question=%r",
        payload.mode, payload.question[:60],
    )
    try:
        result = await service.debate(payload.mode, payload.question)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result
