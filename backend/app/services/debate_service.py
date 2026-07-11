"""Orchestrates the full debate lifecycle.

Coordinates agent calls, domain model mutations, and persistence
to run a multi-round debate from creation through final verdict.
"""

from __future__ import annotations

import logging
from uuid import uuid4

from app.agents.base import AgentContext
from app.agents.registry import AgentRegistry
from app.domain.debate import Argument, Debate, Round, Verdict
from app.domain.enums import AgentRole, DebateStatus
from app.services.llm_service import LLMService
from app.storage.repository import DebateRepository

logger = logging.getLogger("app.services.debate_service")


class DebateNotFoundError(ValueError):
    """Raised when a requested debate ID does not exist in the repository."""

    def __init__(self, debate_id: str) -> None:
        self.debate_id = debate_id
        super().__init__(f"Debate '{debate_id}' not found")


class DebateService:
    """Coordinates debate creation, round execution, and final verdict."""

    def __init__(
        self,
        repository: DebateRepository,
        llm_service: LLMService,
        max_rounds: int = 3,
    ) -> None:
        self._repo = repository
        self._llm = llm_service
        self._max_rounds = max_rounds

    # ── Public API ───────────────────────────────────────────────

    async def create_debate(self, topic: str) -> Debate:
        """Create a new debate and persist it.

        Returns the newly created Debate in PENDING status.
        """
        debate = Debate(id=str(uuid4()), topic=topic)
        self._repo.save(debate)
        logger.info("Created debate %s: topic=%r", debate.id, topic[:60])
        return debate

    async def start_debate(self, debate_id: str) -> Debate:
        """Run all rounds of the debate and return the final state.

        Transitions the debate through IN_PROGRESS → (rounds) → COMPLETED.
        On any failure the debate is marked ERROR and the partial state
        is preserved so the frontend can display what was completed.
        """
        debate = self._repo.get(debate_id)
        if not debate:
            raise DebateNotFoundError(debate_id)

        debate.advance_status(DebateStatus.IN_PROGRESS)
        self._repo.save(debate)

        try:
            for round_num in range(1, self._max_rounds + 1):
                logger.info(
                    "Debate %s  running round %d/%d",
                    debate_id,
                    round_num,
                    self._max_rounds,
                )
                round_ = await self._run_round(debate, round_num)
                debate.add_round(round_)
                self._repo.save(debate)

            logger.info("Debate %s  running final verdict", debate_id)
            await self._run_verdict(debate)
            self._repo.save(debate)
        except Exception:
            logger.exception("Debate %s failed", debate_id)
            debate.advance_status(DebateStatus.ERROR)
            self._repo.save(debate)

        return debate

    def get_debate(self, debate_id: str) -> Debate | None:
        """Retrieve a debate by ID. Returns None when not found."""
        return self._repo.get(debate_id)

    def save_debate(self, debate: Debate) -> None:
        """Persist a debate (public wrapper around repository save)."""
        self._repo.save(debate)

    # ── Internal helpers ─────────────────────────────────────────

    async def _run_round(self, debate: Debate, round_num: int) -> Round:
        """Execute a single debate round: Moderator → Pro → Con."""
        previous = debate.rounds

        # -- 1. Moderator --
        mod_ctx = AgentContext(
            topic=debate.topic,
            round_number=round_num,
            previous_rounds=previous,
            debate_id=debate.id,
        )
        moderator_cls = AgentRegistry.get("moderator")
        moderator_content = await moderator_cls(self._llm).generate(mod_ctx)

        # -- 2. Pro (FOR) --
        pro_ctx = AgentContext(
            topic=debate.topic,
            round_number=round_num,
            previous_rounds=previous,
            moderator_steer=moderator_content,
            debate_id=debate.id,
        )
        pro_cls = AgentRegistry.get("pro")
        pro_content = await pro_cls(self._llm).generate(pro_ctx)

        # -- 3. Con (AGAINST) --
        con_ctx = AgentContext(
            topic=debate.topic,
            round_number=round_num,
            previous_rounds=previous,
            moderator_steer=moderator_content,
            debate_id=debate.id,
        )
        con_cls = AgentRegistry.get("con")
        con_content = await con_cls(self._llm).generate(con_ctx)

        return Round(
            round_number=round_num,
            moderator_steer=moderator_content,
            pro_argument=Argument(role=AgentRole.PRO, content=pro_content),
            con_argument=Argument(role=AgentRole.CON, content=con_content),
        )

    async def _run_verdict(self, debate: Debate) -> None:
        """Invoke the Judge to analyse all rounds and produce a verdict.

        The judge's full output is stored as the summary; the last paragraph
        is extracted as the actionable recommendation.
        """
        judge_ctx = AgentContext(
            topic=debate.topic,
            round_number=self._max_rounds + 1,
            previous_rounds=debate.rounds,
            debate_id=debate.id,
        )
        judge_cls = AgentRegistry.get("judge")
        content = await judge_cls(self._llm).generate(judge_ctx)

        # Heuristic: the last non-empty paragraph is the recommendation.
        paragraphs = [p.strip() for p in content.strip().split("\n\n") if p.strip()]
        recommendation = paragraphs[-1] if len(paragraphs) > 1 else content

        verdict = Verdict(summary=content, recommendation=recommendation)
        debate.set_verdict(verdict)
