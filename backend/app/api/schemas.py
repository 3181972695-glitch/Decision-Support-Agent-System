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
    model_config = {
        "json_schema_extra": {"example": {"topic": "Should I pursue graduate school?"}}
    }


# ── Response Schemas ─────────────────────────────────────────────


class ArgumentResponse(BaseModel):
    """An argument made by an agent in a round."""

    role: str
    content: str
    created_at: datetime | None = None


class RoundResponse(BaseModel):
    """A single round of the debate."""

    round_number: int
    moderator_summary: str | None = None
    moderator_steer: str | None = None
    pro_argument: ArgumentResponse | None = None
    con_argument: ArgumentResponse | None = None


class VerdictResponse(BaseModel):
    """The judge's final verdict."""

    summary: str
    recommendation: str
    created_at: datetime | None = None


class DebateResponse(BaseModel):
    """Full debate state returned to the client."""

    id: str
    topic: str
    status: DebateStatusEnum
    rounds: list[RoundResponse] = []
    verdict: VerdictResponse | None = None
    created_at: datetime
    updated_at: datetime | None = None


class ErrorResponse(BaseModel):
    """Standard error response."""

    detail: str
    error_code: str | None = None
