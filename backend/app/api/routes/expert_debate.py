"""API routes for Expert Debate Mode."""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services.expert_debate_service import ExpertDebateService
from app.services.streaming_expert_service import StreamingExpertDebateService
from app.services.tool_service import ToolService

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


class GeneratedExpert(BaseModel):
    role: str
    expertise: str = ""


class ExpertDebateResponse(BaseModel):
    mode: str
    question: str
    generated_experts: list[GeneratedExpert] = []
    experts: list[ExpertAnalysis]
    debate_rounds: list[DebateRound] = []
    final_decision: str
    confidence: int = 0
    confidence_reason: list[str] = []
    uncertainties: list[str] = []
    key_tradeoffs: list[str] = []


# ── Dependencies ──────────────────────────────────────────────────


def get_expert_debate_service(request: Request) -> ExpertDebateService:
    return request.app.state.expert_debate_service  # type: ignore[no-any-return]


def get_streaming_expert_service(request: Request) -> StreamingExpertDebateService:
    return request.app.state.streaming_expert_service  # type: ignore[no-any-return]


def get_tool_service(request: Request) -> ToolService:
    return request.app.state.tool_service  # type: ignore[no-any-return]


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


@router.post("/debate/stream")
async def expert_debate_stream(
    payload: ExpertDebateRequest,
    request: Request,
    service: StreamingExpertDebateService = Depends(get_streaming_expert_service),
):
    """Stream a multi-expert debate via SSE with real-time token updates."""
    logger.info(
        "[EXPERT_DEBATE] POST /expert/debate/stream mode=%s question=%r",
        payload.mode, payload.question[:60],
    )

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            async for event in service.stream_debate(payload.mode, payload.question):
                yield event
        except Exception as exc:
            logger.exception("[EXPERT_DEBATE] stream error: %s", exc)
            import json
            yield f"event: error\ndata: {json.dumps({'message': str(exc)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.get("/tools")
async def list_available_tools(
    service: ToolService = Depends(get_tool_service),
):
    """List all available tools for expert debate."""
    return {"tools": service.list_tools()}
