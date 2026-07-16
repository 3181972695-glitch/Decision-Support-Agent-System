"""Pure domain models for the Debate aggregate.

No framework or infrastructure imports — this module is the innermost
layer of the architecture and must remain free of external dependencies.
"""

from __future__ import annotations

import re
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
    evidence: list[Evidence] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __str__(self) -> str:
        return f"[{self.role.value.upper()}]\n{self.content}"



@dataclass
class JudgeEvaluation:
    """Structured evaluation produced by the judge.

    Attributes:
        winner: Which side won ('pro' or 'con').
        scores: Per-dimension scores (0-100).
        confidence: Judge's confidence in the verdict (0.0-1.0).
        strengths: Key strengths of the winning side.
        weaknesses: Key weaknesses of the losing side.
    """

    winner: str
    scores: dict[str, int]
    confidence: float
    strengths: list[str]
    weaknesses: list[str]

    @classmethod
    def from_dict(cls, data: dict) -> "JudgeEvaluation":
        """Parse a dict (from JSON) into a JudgeEvaluation, with defaults."""
        scores = data.get("scores", {})
        if not isinstance(scores, dict):
            scores = {}
        return cls(
            winner=data.get("winner", ""),
            scores={k: int(v) for k, v in scores.items() if isinstance(v, (int, float))},
            confidence=float(data.get("confidence", 0.0)),
            strengths=data.get("strengths", []) if isinstance(data.get("strengths"), list) else [],
            weaknesses=data.get("weaknesses", []) if isinstance(data.get("weaknesses"), list) else [],
        )

    def to_dict(self) -> dict:
        return {
            "winner": self.winner,
            "scores": self.scores,
            "confidence": self.confidence,
            "strengths": self.strengths,
            "weaknesses": self.weaknesses,
        }



@dataclass
class RoundMemory:
    """Compact summary of a round for use in subsequent prompts.

    Stored separately from full round text to avoid prompt inflation.
    Each round's memory is generated from the moderator_summary after the round completes.

    Attributes:
        pro_claim: The Pro side's main claim in this round.
        con_claim: The Con side's main claim in this round.
        strongest_evidence: The most compelling evidence presented.
        remaining_disagreement: Key points of disagreement that remain.
        moderator_takeaway: The moderator's overall takeaway.
    """

    pro_claim: str = ""
    con_claim: str = ""
    strongest_evidence: str = ""
    remaining_disagreement: str = ""
    moderator_takeaway: str = ""

    def to_compact_str(self) -> str:
        """Format memory as a compact string for prompt injection."""
        parts = []
        if self.pro_claim:
            parts.append(f"Pro: {self.pro_claim[:150]}")
        if self.con_claim:
            parts.append(f"Con: {self.con_claim[:150]}")
        if self.strongest_evidence:
            parts.append(f"Evidence: {self.strongest_evidence[:120]}")
        if self.remaining_disagreement:
            parts.append(f"Disagree: {self.remaining_disagreement[:120]}")
        if self.moderator_takeaway:
            parts.append(f"Takeaway: {self.moderator_takeaway[:150]}")
        return " | ".join(parts)

    @classmethod
    def from_moderator_summary(cls, summary: str) -> "RoundMemory":
        """Extract memory fields from a moderator summary using heuristics."""
        mem = cls()
        if not summary:
            return mem
        # Try to extract structured info from the summary text
        mem.moderator_takeaway = summary[:300]
        # Look for Pro/Con mentions
        pro_match = re.search(r'(?:Pro|支持方|찬성)[^.]*\.', summary)
        if pro_match:
            mem.pro_claim = pro_match.group(0)[:200]
        con_match = re.search(r'(?:Con|反对方|반대)[^.]*\.', summary)
        if con_match:
            mem.con_claim = con_match.group(0)[:200]
        return mem



@dataclass
class Evidence:
    """A piece of evidence supporting an argument.

    Attributes:
        claim: The claim being made.
        evidence: Supporting evidence/facts.
        reasoning: How the evidence supports the claim.
    """

    claim: str = ""
    evidence: str = ""
    reasoning: str = ""


@dataclass
class CrossExaminationQA:
    """A single cross-examination question and answer pair.

    Attributes:
        question_role:  Which agent asked the question.
        question:       The question text.
        answer_role:    Which agent answered the question.
        answer:         The answer text.
    """

    question_role: AgentRole
    question: str
    answer_role: AgentRole
    answer: str


@dataclass
class UserQuestionQA:
    """A question asked by the user during a debate pause, with the agent's answer.

    Attributes:
        target_role:  Which agent was asked (pro / con / moderator).
        question:     The user's question.
        answer:       The agent's answer.
    """

    target_role: AgentRole
    question: str
    answer: str


# ─────────────────────────────────────────────────────────────────
#  Entities
# ─────────────────────────────────────────────────────────────────


@dataclass
class Round:
    """A single round of the structured debate.

    Each round follows an organised flow:
        Moderator intro → Pro opening → Con opening →
        Cross-examination → Pro rebuttal → Con rebuttal →
        Moderator summary

    Attributes:
        round_number:       1-indexed round number.
        round_focus:        The focus/objective for this round.
        moderator_intro:    The moderator's introduction and guidance for this round.
        pro_opening:        The Pro agent's opening argument.
        con_opening:        The Con agent's opening argument.
        cross_examination:  List of cross-examination question-answer pairs.
        pro_rebuttal:       The Pro agent's rebuttal to Con's arguments.
        con_rebuttal:       The Con agent's rebuttal to Pro's arguments.
        user_questions:     Questions asked by the user during the debate pause.
        moderator_summary:  The moderator's summary after all arguments in this round.
        moderator_steer:    The moderator's guidance/direction for the next round.

    """

    round_number: int
    round_focus: Optional[str] = None
    moderator_intro: Optional[str] = None
    pro_opening: Optional[Argument] = None
    con_opening: Optional[Argument] = None
    cross_examination: list[CrossExaminationQA] = field(default_factory=list)
    pro_rebuttal: Optional[Argument] = None
    con_rebuttal: Optional[Argument] = None
    user_questions: list[UserQuestionQA] = field(default_factory=list)
    moderator_summary: Optional[str] = None
    moderator_steer: Optional[str] = None
    memory: RoundMemory | None = None

    def __str__(self) -> str:
        parts = [f"=== Round {self.round_number} ==="]
        if self.round_focus:
            parts.append(f"[FOCUS] {self.round_focus}")
        if self.moderator_intro:
            parts.append(f"[MODERATOR INTRO]\n{self.moderator_intro}")
        if self.pro_opening:
            parts.append(str(self.pro_opening))
        if self.con_opening:
            parts.append(str(self.con_opening))
        for qa in self.cross_examination:
            parts.append(
                f"[CROSS-EXAM] {qa.question_role.value.upper()} asks: {qa.question}"
            )
            parts.append(
                f"[CROSS-EXAM] {qa.answer_role.value.upper()} answers: {qa.answer}"
            )
        if self.pro_rebuttal:
            parts.append(f"[PRO REBUTTAL]\n{self.pro_rebuttal.content}")
        if self.con_rebuttal:
            parts.append(f"[CON REBUTTAL]\n{self.con_rebuttal.content}")
        for uq in self.user_questions:
            parts.append(f"[USER] → {uq.target_role.value.upper()}: {uq.question}")
            parts.append(f"[{uq.target_role.value.upper()} ANSWER]: {uq.answer}")
        if self.moderator_summary:
            parts.append(f"[MODERATOR SUMMARY]\n{self.moderator_summary}")
        if self.moderator_steer:
            parts.append(f"[MODERATOR STEER]\n{self.moderator_steer}")
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
    evaluation: JudgeEvaluation | None = None
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
        max_rounds: Number of rounds to run (default 3). Judge runs after final round.
        status:     Current lifecycle status (pending → in_progress → completed).
        rounds:     Ordered list of completed rounds.
        verdict:    The judge's final verdict, set after the last round.
        created_at: Timestamp of creation.
        updated_at: Timestamp of the most recent state change.
    """

    id: str
    topic: str
    max_rounds: int = 3
    status: DebateStatus = DebateStatus.PENDING
    rounds: list[Round] = field(default_factory=list)
    verdict: Optional[Verdict] = None
    awaiting_input: bool = False
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
