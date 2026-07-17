"""API routes for debate management."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.schemas import (
    ArgumentResponse,
    CrossExaminationResponse,
    DebateCreate,
    DebateResponse,
    DebateStatusEnum,
    QuestionsSubmit,
    RoundResponse,
    UserQuestionResponse,
    VerdictResponse,
)
from app.domain.enums import AgentRole, DebateStatus
from app.services.debate_service import (
    DebateNotFoundError,
    DebateService,
)

logger = logging.getLogger("app.api.debates")

router = APIRouter(prefix="/debates", tags=["debates"])

# ── Background task tracking ────────────────────────────────────
_background_tasks: set[asyncio.Task[None]] = set()


def _cleanup_done_task(task: asyncio.Task[None]) -> None:
    """Remove a finished background task from the tracking set."""
    _background_tasks.discard(task)


# ── Dependency injection via app.state ──────────────────────────


def get_debate_service(request: Request) -> DebateService:
    """Dependency provider: returns the DebateService from app.state.

    The service is set during FastAPI lifespan (see main.py).
    Tests can override this via app.dependency_overrides.
    """
    return request.app.state.debate_service  # type: ignore[no-any-return]


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


def _cross_exam_to_response(qa: object) -> CrossExaminationResponse:
    """Convert a domain CrossExaminationQA to a response schema."""
    q_role = getattr(qa, "question_role", AgentRole.PRO).value
    a_role = getattr(qa, "answer_role", AgentRole.CON).value
    question = getattr(qa, "question", "")
    answer = getattr(qa, "answer", "")
    logger.info(
        "[XDIAG] API_SERIALIZE q_role=%s a_role=%s q_len=%d q_preview=%r a_len=%d a_preview=%r",
        q_role, a_role, len(question), question[:80], len(answer), answer[:80],
    )
    return CrossExaminationResponse(
        question_role=q_role,
        question=question,
        answer_role=a_role,
        answer=answer,
    )


def _user_question_to_response(uq: object) -> UserQuestionResponse:
    """Convert a domain UserQuestionQA to a response schema."""
    return UserQuestionResponse(
        target_role=getattr(uq, "target_role", AgentRole.MODERATOR).value,
        question=getattr(uq, "question", ""),
        answer=getattr(uq, "answer", ""),
    )


def _round_to_response(round_: object) -> RoundResponse:
    """Convert a domain Round to a response schema."""
    return RoundResponse(
        round_number=getattr(round_, "round_number", 0),
        round_focus=getattr(round_, "round_focus", None),
        moderator_intro=getattr(round_, "moderator_intro", None),
        pro_opening=_argument_to_response(getattr(round_, "pro_opening", None)),
        con_opening=_argument_to_response(getattr(round_, "con_opening", None)),
        cross_examination=[
            _cross_exam_to_response(qa)
            for qa in getattr(round_, "cross_examination", [])
        ],
        pro_rebuttal=_argument_to_response(getattr(round_, "pro_rebuttal", None)),
        con_rebuttal=_argument_to_response(getattr(round_, "con_rebuttal", None)),
        user_questions=[
            _user_question_to_response(uq)
            for uq in getattr(round_, "user_questions", [])
        ],
        moderator_summary=getattr(round_, "moderator_summary", None),
        moderator_steer=getattr(round_, "moderator_steer", None),
    )


def _verdict_to_response(verdict: object | None) -> VerdictResponse | None:
    """Convert a domain Verdict to a response schema."""
    if verdict is None:
        return None
    from app.api.schemas import JudgeEvaluationResponse
    evaluation = getattr(verdict, "evaluation", None)
    eval_resp = None
    if evaluation is not None:
        eval_resp = JudgeEvaluationResponse(
            winner=getattr(evaluation, "winner", ""),
            scores=getattr(evaluation, "scores", {}),
            confidence=getattr(evaluation, "confidence", 0.0),
            strengths=getattr(evaluation, "strengths", []),
            weaknesses=getattr(evaluation, "weaknesses", []),
        )
    return VerdictResponse(
        summary=getattr(verdict, "summary", ""),
        recommendation=getattr(verdict, "recommendation", ""),
        evaluation=eval_resp,
        created_at=getattr(verdict, "created_at", None),
    )


def _debate_to_response(debate: object) -> DebateResponse:
    """Convert a domain Debate to a response schema."""
    rounds_list = getattr(debate, "rounds", [])
    return DebateResponse(
        id=getattr(debate, "id", ""),
        topic=getattr(debate, "topic", ""),
        max_rounds=getattr(debate, "max_rounds", 3),
        status=DebateStatusEnum(getattr(debate, "status", "pending").value),
        rounds=[_round_to_response(r) for r in rounds_list],
        verdict=_verdict_to_response(getattr(debate, "verdict", None)),
        awaiting_input=getattr(debate, "awaiting_input", False),
        created_at=getattr(debate, "created_at", datetime.now()),
        updated_at=getattr(debate, "updated_at", None),
    )
    logger.info(
        "[XDIAG] SERIALIZE debate id=%s awaiting_input=%s rounds=%d",
        getattr(debate, "id", ""), getattr(debate, "awaiting_input", False), len(rounds_list),
    )


# ── Routes ──────────────────────────────────────────────────────


@router.post("/", response_model=DebateResponse, status_code=201)
async def create_debate(
    payload: DebateCreate,
    service: DebateService = Depends(get_debate_service),
):
    """Create a new debate for the given topic with configurable options."""
    debate = await service.create_debate(
        topic=payload.topic,
        max_rounds=payload.max_rounds,
        enable_cross_exam=payload.enable_cross_exam,
        enable_moderator=payload.enable_moderator,
        enable_user_questions=payload.enable_user_questions,
    )
    logger.info(
        "Created debate %s: topic=%r  max_rounds=%d  cross_exam=%s  moderator=%s",
        debate.id,
        payload.topic[:60],
        payload.max_rounds,
        payload.enable_cross_exam,
        payload.enable_moderator,
    )
    return _debate_to_response(debate)


@router.get("/{debate_id}", response_model=DebateResponse)
async def get_debate(
    debate_id: str,
    service: DebateService = Depends(get_debate_service),
):
    """Retrieve the current state of a debate, including awaiting_input."""
    debate = await service.get_debate(debate_id)
    if debate is None:
        raise HTTPException(
            status_code=404,
            detail=f"Debate '{debate_id}' not found",
        )
    logger.info("[TRACE] >>> HTTP GET /debate/%s status=%s rounds=%d <<<", debate_id, debate.status.value, len(debate.rounds))
    resp = _debate_to_response(debate)
    logger.info(
        "[TRACE] >>> HTTP RESPONSE debate=%s status=%s awaiting_input=%s rounds=%d <<<",
        debate_id, resp.status, resp.awaiting_input, len(resp.rounds),
    )
    return resp


@router.post("/{debate_id}/start", response_model=DebateResponse)
async def start_debate(
    debate_id: str,
    service: DebateService = Depends(get_debate_service),
):
    """Start the debate pipeline in the background and return immediately."""
    debate = await service.get_debate(debate_id)
    if debate is None:
        raise HTTPException(
            status_code=404,
            detail=f"Debate '{debate_id}' not found",
        )

    if debate.is_completed():
        raise HTTPException(status_code=400, detail="Debate is already completed")

    debate.advance_status(DebateStatus.IN_PROGRESS)
    await service.save_debate(debate)

    logger.info("[TRACE] >>> HTTP POST /start debate=%s creating background task <<<", debate_id)
    task = asyncio.create_task(service.start_debate(debate_id))
    _background_tasks.add(task)
    task.add_done_callback(_cleanup_done_task)

    return _debate_to_response(debate)


@router.post("/{debate_id}/continue", response_model=DebateResponse)
async def continue_debate(
    debate_id: str,
    service: DebateService = Depends(get_debate_service),
):
    """Signal the debate to continue to the next round."""
    logger.info("[TRACE] >>> HTTP POST /continue debate=%s <<<", debate_id)
    try:
        debate = await service.continue_debate(debate_id)
    except DebateNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return _debate_to_response(debate)


@router.post("/{debate_id}/questions", response_model=DebateResponse)
async def submit_questions(
    debate_id: str,
    payload: QuestionsSubmit,
    service: DebateService = Depends(get_debate_service),
):
    """Submit optional user questions during a debate pause.

    Generates answers from the Pro and Con agents and stores them
    on the current round. Call this before POST /continue.
    """
    logger.info("[TRACE] >>> HTTP POST /questions debate=%s <<<", debate_id)
    try:
        debate = await service.submit_questions(
            debate_id,
            pro_question=payload.pro_question,
            con_question=payload.con_question,
        )
    except DebateNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return _debate_to_response(debate)


@router.get("/{debate_id}/rounds/{round_number}", response_model=RoundResponse)
async def get_round(
    debate_id: str,
    round_number: int,
    service: DebateService = Depends(get_debate_service),
):
    """Retrieve a specific round of a debate."""
    debate = await service.get_debate(debate_id)
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

# ── Performance endpoint ────────────────────────────────────────


@router.get("/{debate_id}/performance")
async def get_debate_performance(
    debate_id: str,
    request: Request,
):
    """Return performance summary for a completed debate."""
    service: DebateService = request.app.state.debate_service
    debate = await service.get_debate(debate_id)
    if debate is None:
        raise HTTPException(status_code=404, detail=f"Debate '{debate_id}' not found")

    profiler = service._llm.get_profiler()
    if profiler is None:
        return {
            "debate_id": debate_id,
            "status": debate.status.value,
            "rounds": len(debate.rounds),
            "message": "No profiling data available — profiler was not started",
        }

    perf = profiler.summary()
    perf["debate_id"] = debate_id
    perf["status"] = debate.status.value
    perf["rounds_completed"] = len(debate.rounds)
    return perf
