"""SQLAlchemy-based implementation of DebateRepository.

Uses aiosqlite (SQLite) by default, trivially swappable to PostgreSQL
by changing the DATABASE_URL. Rounds and verdicts are stored as JSON
columns to keep the schema simple.

The repository is synchronous on the outside (matching the
DebateRepository ABC) and uses asyncio.run() internally to bridge
the async SQLAlchemy session.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.domain.debate import (
    Argument,
    CrossExaminationQA,
    Debate,
    Round,
    UserQuestionQA,
    Verdict,
)
from app.domain.enums import AgentRole, DebateStatus
from app.storage.models import Base, DebateRow
from app.storage.repository import DebateRepository

logger = logging.getLogger("app.storage.sql_repository")


class SqlDebateRepository(DebateRepository):
    """Persists debates to SQLite via SQLAlchemy async.

    Uses asyncio.run() internally to provide a synchronous interface
    that matches the DebateRepository ABC. For production deployments
    with PostgreSQL, consider upgrading to an async service layer.
    """

    def __init__(self, database_url: str = "sqlite+aiosqlite:///debates.db") -> None:
        self._engine = create_async_engine(database_url, echo=False)
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)

    async def _init_db(self) -> None:
        """Create tables if they don't exist. Call once at startup."""
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def save(self, debate: Debate) -> None:
        await self._save_async(debate)

    async def get(self, debate_id: str) -> Debate | None:
        return await self._get_async(debate_id)

    async def list(self) -> list[Debate]:
        return await self._list_async()

    async def delete(self, debate_id: str) -> None:
        await self._delete_async(debate_id)

    async def exists(self, debate_id: str) -> bool:
        return await self._exists_async(debate_id)

    # ── Async implementations ──────────────────────────────────

    async def _save_async(self, debate: Debate) -> None:
        async with self._session_factory() as session:
            row = await session.get(DebateRow, debate.id)
            if row is None:
                row = DebateRow(id=debate.id)
                session.add(row)

            row.topic = debate.topic
            row.max_rounds = debate.max_rounds
            row.status = debate.status.value
            row.awaiting_input = debate.awaiting_input
            row.created_at = debate.created_at
            row.updated_at = debate.updated_at
            row.rounds_json = json.dumps(
                [_round_to_dict(r) for r in debate.rounds],
                default=str,
            )
            row.verdict_json = (
                json.dumps(_verdict_to_dict(debate.verdict), default=str)
                if debate.verdict
                else None
            )

            await session.commit()

    async def _get_async(self, debate_id: str) -> Debate | None:
        async with self._session_factory() as session:
            row = await session.get(DebateRow, debate_id)
            if row is None:
                return None
            return _row_to_debate(row)

    async def _list_async(self) -> list[Debate]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(DebateRow).order_by(DebateRow.created_at)
            )
            return [_row_to_debate(row) for row in result.scalars()]

    async def _delete_async(self, debate_id: str) -> None:
        async with self._session_factory() as session:
            row = await session.get(DebateRow, debate_id)
            if row is not None:
                await session.delete(row)
                await session.commit()

    async def _exists_async(self, debate_id: str) -> bool:
        async with self._session_factory() as session:
            row = await session.get(DebateRow, debate_id)
            return row is not None


# ── JSON serialization helpers ──────────────────────────────────


def _round_to_dict(round_: Round) -> dict:
    return {
        "round_number": round_.round_number,
        "round_focus": round_.round_focus,
        "moderator_intro": round_.moderator_intro,
        "pro_opening": _argument_to_dict(round_.pro_opening),
        "con_opening": _argument_to_dict(round_.con_opening),
        "cross_examination": [
            {
                "question_role": qa.question_role.value,
                "question": qa.question,
                "answer_role": qa.answer_role.value,
                "answer": qa.answer,
            }
            for qa in round_.cross_examination
        ],
        "pro_rebuttal": _argument_to_dict(round_.pro_rebuttal),
        "con_rebuttal": _argument_to_dict(round_.con_rebuttal),
        "user_questions": [
            {
                "target_role": uq.target_role.value,
                "question": uq.question,
                "answer": uq.answer,
            }
            for uq in round_.user_questions
        ],
        "moderator_summary": round_.moderator_summary,
        "moderator_steer": round_.moderator_steer,
    }


def _argument_to_dict(arg: Argument | None) -> dict | None:
    if arg is None:
        return None
    return {
        "role": arg.role.value,
        "content": arg.content,
        "created_at": arg.created_at.isoformat(),
    }


def _verdict_to_dict(verdict: Verdict | None) -> dict | None:
    if verdict is None:
        return None
    return {
        "summary": verdict.summary,
        "recommendation": verdict.recommendation,
        "created_at": verdict.created_at.isoformat(),
    }


def _row_to_debate(row: DebateRow) -> Debate:
    rounds_data = json.loads(row.rounds_json) if row.rounds_json else []
    verdict_data = json.loads(row.verdict_json) if row.verdict_json else None

    return Debate(
        id=row.id,
        topic=row.topic,
        max_rounds=row.max_rounds,
        status=DebateStatus(row.status),
        rounds=[_dict_to_round(r) for r in rounds_data],
        verdict=_dict_to_verdict(verdict_data) if verdict_data else None,
        awaiting_input=row.awaiting_input,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _dict_to_round(data: dict) -> Round:
    return Round(
        round_number=data["round_number"],
        round_focus=data.get("round_focus"),
        moderator_intro=data.get("moderator_intro"),
        pro_opening=_dict_to_argument(data.get("pro_opening")),
        con_opening=_dict_to_argument(data.get("con_opening")),
        cross_examination=[
            CrossExaminationQA(
                question_role=AgentRole(qa["question_role"]),
                question=qa["question"],
                answer_role=AgentRole(qa["answer_role"]),
                answer=qa["answer"],
            )
            for qa in data.get("cross_examination", [])
        ],
        pro_rebuttal=_dict_to_argument(data.get("pro_rebuttal")),
        con_rebuttal=_dict_to_argument(data.get("con_rebuttal")),
        user_questions=[
            UserQuestionQA(
                target_role=AgentRole(uq["target_role"]),
                question=uq["question"],
                answer=uq["answer"],
            )
            for uq in data.get("user_questions", [])
        ],
        moderator_summary=data.get("moderator_summary"),
        moderator_steer=data.get("moderator_steer"),
    )


def _dict_to_argument(data: dict | None) -> Argument | None:
    if data is None:
        return None
    return Argument(
        role=AgentRole(data["role"]),
        content=data["content"],
        created_at=datetime.fromisoformat(data["created_at"]),
    )


def _dict_to_verdict(data: dict | None) -> Verdict | None:
    if data is None:
        return None
    return Verdict(
        summary=data["summary"],
        recommendation=data["recommendation"],
        created_at=datetime.fromisoformat(data["created_at"]),
    )
