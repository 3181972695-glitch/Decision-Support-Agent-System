"""API routes for Expert Mode analysis."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.services.expert_service import ExpertService

logger = logging.getLogger("app.api.routes.expert")

router = APIRouter(prefix="/expert", tags=["expert"])


# ── Schemas ──────────────────────────────────────────────────────


class ExpertAnalyzeRequest(BaseModel):
    mode: str = Field(..., description="Expert mode key (e.g. 'software', 'career')")
    question: str = Field(..., min_length=1, max_length=2000, description="Question to analyze")


class ExpertAnalysis(BaseModel):
    role: str
    analysis: str


class ExpertAnalyzeResponse(BaseModel):
    mode: str
    question: str
    experts: list[ExpertAnalysis]
    final_decision: str


# ── Dependency ───────────────────────────────────────────────────


def get_expert_service(request: Request) -> ExpertService:
    """Return the ExpertService from app.state (set during lifespan)."""
    return request.app.state.expert_service  # type: ignore[no-any-return]


# ── Routes ───────────────────────────────────────────────────────


@router.post("/analyze", response_model=ExpertAnalyzeResponse)
async def expert_analyze(
    payload: ExpertAnalyzeRequest,
    service: ExpertService = Depends(get_expert_service),
):
    """Run a multi-expert analysis for the given mode and question."""
    logger.info(
        "[EXPERT] POST /expert/analyze mode=%s question=%r",
        payload.mode, payload.question[:60],
    )
    try:
        result = await service.analyze(payload.mode, payload.question)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result
