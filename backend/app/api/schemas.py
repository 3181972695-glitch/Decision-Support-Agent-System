"""Pydantic schemas for API request/response models."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class DebateStatusEnum(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ERROR = "error"


# ── Request Schemas ──────────────────────────────────────────────


class DebateCreate(BaseModel):
    """Request body to create a new debate."""

    topic: str = Field(
        ..., min_length=1, max_length=500, description="The debate topic"
    )
    max_rounds: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Number of debate rounds (judge runs after the final round)",
    )
    enable_cross_exam: bool = Field(
        default=True,
        description="Enable cross-examination between Pro and Con agents",
    )
    enable_moderator: bool = Field(
        default=True,
        description="Enable moderator introductions and summaries",
    )
    enable_user_questions: bool = Field(
        default=False,
        description="Enable user questions to Pro and Con after each round",
    )
    model_config = {
        "json_schema_extra": {
            "example": {
                "topic": "Should I pursue graduate school?",
                "max_rounds": 3,
                "enable_cross_exam": True,
                "enable_moderator": True,
            }
        }
    }


# ── Response Schemas ─────────────────────────────────────────────


class ArgumentResponse(BaseModel):
    role: str
    content: str
    created_at: datetime | None = None


class CrossExaminationResponse(BaseModel):
    question_role: str
    question: str
    answer_role: str
    answer: str


class UserQuestionResponse(BaseModel):
    target_role: str
    question: str
    answer: str


class RoundResponse(BaseModel):
    round_number: int
    round_focus: str | None = None
    moderator_intro: str | None = None
    pro_opening: ArgumentResponse | None = None
    con_opening: ArgumentResponse | None = None
    cross_examination: list[CrossExaminationResponse] = []
    pro_rebuttal: ArgumentResponse | None = None
    con_rebuttal: ArgumentResponse | None = None
    user_questions: list[UserQuestionResponse] = []
    moderator_summary: str | None = None
    moderator_steer: str | None = None



class JudgeEvaluationResponse(BaseModel):
    """Structured evaluation from the judge."""
    winner: str = ""
    scores: dict[str, int] = Field(default_factory=dict)
    confidence: float = 0.0
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)


class VerdictResponse(BaseModel):
    summary: str
    recommendation: str
    evaluation: JudgeEvaluationResponse | None = None
    created_at: datetime | None = None


class DebateResponse(BaseModel):
    id: str
    topic: str
    max_rounds: int = 3
    status: DebateStatusEnum
    rounds: list[RoundResponse] = []
    verdict: VerdictResponse | None = None
    awaiting_input: bool = False
    created_at: datetime
    updated_at: datetime | None = None


class ErrorResponse(BaseModel):
    detail: str
    error_code: str | None = None


class QuestionsSubmit(BaseModel):
    """Optional user questions submitted during a debate pause."""
    pro_question: str = Field(default="", description="Question for the Pro agent")
    con_question: str = Field(default="", description="Question for the Con agent")
