"""Pure domain models for the Debate aggregate.

No framework or infrastructure imports — this module is the innermost
layer of the architecture and must remain free of external dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from app.domain.enums import AgentRole, DebateStatus


# ─────────────────────────────────────────────────────────────────
#  Value Objects
# ─────────────────────────────────────────────────────────────────


@dataclass
class Argument:
    """An argument made by an agent in a single debate round.

    Attributes:
        role:   Which agent produced this argument (pro / con).
        content: The argument text.
        created_at: Timestamp of when this argument was generated.
    """

    role: AgentRole
    content: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __str__(self) -> str:
        return f"[{self.role.value.upper()}]\n{self.content}"


# ─────────────────────────────────────────────────────────────────
#  Entities
# ─────────────────────────────────────────────────────────────────


@dataclass
class Round:
    """A single round of the debate.

    A round consists of the moderator's input (summary of the prior
    round plus a steer for the next one) and the two opposing arguments.

    Attributes:
        round_number:      1-indexed round number.
        moderator_summary: The moderator's recap of the previous round.
        moderator_steer:   The moderator's guidance/direction for this round.
        pro_argument:      The Pro agent's argument for this round.
        con_argument:      The Con agent's argument for this round.
    """

    round_number: int
    moderator_summary: Optional[str] = None
    moderator_steer: Optional[str] = None
    pro_argument: Optional[Argument] = None
    con_argument: Optional[Argument] = None

    def __str__(self) -> str:
        parts = [f"=== Round {self.round_number} ==="]
        if self.moderator_summary:
            parts.append(f"[MODERATOR SUMMARY]\n{self.moderator_summary}")
        if self.moderator_steer:
            parts.append(f"[MODERATOR STEER]\n{self.moderator_steer}")
        if self.pro_argument:
            parts.append(str(self.pro_argument))
        if self.con_argument:
            parts.append(str(self.con_argument))
        return "\n\n".join(parts)


@dataclass
class Verdict:
    """The judge's final verdict after all rounds have completed.

    Attributes:
        summary:        A balanced summary of both sides' arguments.
        recommendation: The judge's final recommendation to the user.
        created_at:     Timestamp of when the verdict was rendered.
    """

    summary: str
    recommendation: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ─────────────────────────────────────────────────────────────────
#  Aggregate Root
# ─────────────────────────────────────────────────────────────────


@dataclass
class Debate:
    """Aggregate root for a debate session.

    A Debate owns its Rounds and Verdict. All mutations to the debate
    state happen through methods on this class.

    Attributes:
        id:         Unique identifier for this debate.
        topic:      The decision question being debated.
        status:     Current lifecycle status (pending → in_progress → completed).
        rounds:     Ordered list of completed rounds.
        verdict:    The judge's final verdict, set after round 3.
        created_at: Timestamp of creation.
        updated_at: Timestamp of the most recent state change.
    """

    id: str
    topic: str
    status: DebateStatus = DebateStatus.PENDING
    rounds: list[Round] = field(default_factory=list)
    verdict: Optional[Verdict] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

    # ── Commands ───────────────────────────────────────────────

    def add_round(self, round_: Round) -> None:
        """Append a completed round to the debate."""
        self.rounds.append(round_)
        self._touch()

    def advance_status(self, new_status: DebateStatus) -> None:
        """Transition the debate to a new lifecycle status."""
        self.status = new_status
        self._touch()

    def set_verdict(self, verdict: Verdict) -> None:
        """Set the judge's verdict and mark the debate as completed."""
        self.verdict = verdict
        self.advance_status(DebateStatus.COMPLETED)

    # ── Queries ────────────────────────────────────────────────

    def latest_round(self) -> Optional[Round]:
        """Return the most recently completed round, or None if no rounds exist."""
        return self.rounds[-1] if self.rounds else None

    def is_completed(self) -> bool:
        """Return True when the debate has reached a terminal status."""
        return self.status in (DebateStatus.COMPLETED, DebateStatus.ERROR)

    # ── Internal helpers ───────────────────────────────────────

    def _touch(self) -> None:
        """Update the timestamp to the current UTC time."""
        self.updated_at = datetime.now(timezone.utc)
