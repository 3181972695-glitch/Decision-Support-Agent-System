"""SQLAlchemy ORM models for debate persistence.

These models are purely infrastructure — they never leak into the
domain layer. The SqlDebateRepository translates between ORM rows
and domain dataclasses.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class DebateRow(Base):
    """A single debate, stored as a row with JSON-encoded rounds and verdict.

    The rounds and verdict are serialized as JSON text columns. This
    keeps the schema simple — no join tables for the nested value objects.
    """

    __tablename__ = "debates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    max_rounds: Mapped[int] = mapped_column(Integer, default=3)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    awaiting_input: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # JSON-encoded aggregates
    rounds_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    verdict_json: Mapped[str | None] = mapped_column(Text, nullable=True)
