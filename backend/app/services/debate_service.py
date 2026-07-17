"""Orchestrates the full debate lifecycle.

Each round follows an optimised parallel flow:
    Stage 1: moderator_intro + pro_opening + con_opening  (parallel)
    Stage 2: pro_ask + con_ask + pro_rebuttal + con_rebuttal  (parallel)
    Stage 3: con_answer + pro_answer  (parallel)
    Stage 4: moderator_summary (serial, depends on all above)
"""

from __future__ import annotations

import asyncio
import time
import json
import logging
import re
from uuid import uuid4

from app.agents.base import AgentContext, BaseAgent, detect_language
from app.agents.moderator import get_round_focus
from app.agents.registry import AgentRegistry
from app.config import settings
from app.domain.debate import (
    Argument,
    CrossExaminationQA,
    Debate,
    Round,
    RoundMemory,
    UserQuestionQA,
    Verdict,
)
from app.domain.enums import AgentRole, DebateStatus, ResponseType
from app.services.llm_service import LLMService

from app.services.event_queue import (
    EventType,
    SSEEvent,
    get_event_queue_registry,
)
from app.storage.repository import DebateRepository

logger = logging.getLogger("app.services.debate_service")


class DebateNotFoundError(ValueError):
    def __init__(self, debate_id: str) -> None:
        self.debate_id = debate_id
        super().__init__(f"Debate '{debate_id}' not found")


class DebateAlreadyRunningError(ValueError):
    def __init__(self, debate_id: str) -> None:
        super().__init__(f"Debate '{debate_id}' is already running or completed")


class DebateService:
    """Coordinates debate creation, round execution, and final verdict."""

    def __init__(
        self,
        repository: DebateRepository,
        llm_service: LLMService,
        agent_models: dict[str, str] | None = None,
    ) -> None:
        self._repo = repository
        self._llm = llm_service
        self._agent_models = agent_models or {}
        self._llm_call_count = 0
        self._continue_events: dict[str, asyncio.Event] = {}

    # ── Model & token routing ────────────────────────────────────

    def _resolve_model(self, role: str) -> str | None:
        if role == "moderator" and settings.MODERATOR_MODEL:
            model = settings.MODERATOR_MODEL
        elif role in ("pro", "con") and settings.ARGUMENT_MODEL:
            model = settings.ARGUMENT_MODEL
        elif role == "judge" and settings.JUDGE_MODEL:
            model = settings.JUDGE_MODEL
        else:
            model = self._agent_models.get(role, settings.LLM_MODEL)
        logger.info("[MODEL_ROUTING] role=%s -> %s", role, model)
        return model

    def _resolve_max_tokens(self, response_type: ResponseType) -> int:
        mapping = {
            ResponseType.MODERATOR_INTRO: settings.MODERATOR_MAX_TOKENS,
            ResponseType.MODERATOR_SUMMARY: settings.MODERATOR_MAX_TOKENS,
            ResponseType.OPENING: settings.OPENING_MAX_TOKENS,
            ResponseType.REBUTTAL: settings.REBUTTAL_MAX_TOKENS,
            ResponseType.CROSS_EXAMINE_ASK: settings.CROSS_EXAM_MAX_TOKENS,
            ResponseType.CROSS_EXAMINE_ANSWER: settings.CROSS_EXAM_MAX_TOKENS,
            ResponseType.USER_ANSWER: settings.OPENING_MAX_TOKENS,
        }
        return mapping.get(response_type, settings.LLM_MAX_TOKENS)

    def _emit(self, debate_id: str, event_type: str, **data: object) -> None:
        role = data.get("role", "")
        rn = data.get("round_number", "")
        if role:
            logger.info("[TRACE] SSE emit type=%s role=%s round=%s debate=%s", event_type, role, rn, debate_id)
        else:
            logger.info("[TRACE] SSE emit type=%s debate=%s", event_type, debate_id)
        registry = get_event_queue_registry()
        registry.push(
            debate_id,
            SSEEvent(event_type=event_type, data={k: v for k, v in data.items()}),
        )

    def _emit_error(self, debate_id: str, message: str) -> None:
        self._emit(debate_id, EventType.DEBATE_ERROR, message=message)

    async def _stream_agent(
        self,
        role: str,
        context: AgentContext,
        debate_id: str,
        round_number: int,
        response_format: dict[str, str] | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Generate a response from an agent with streaming, emitting events.

        SSE events use a display_role that distinguishes moderator_intro
        from moderator_summary so the frontend can render them differently.
        CancelledError is re-raised so cancellation propagates correctly.
        """
        # Derive display role for SSE based on role + response_type.
        # The frontend applyChunk() expects these exact role strings to route
        # streaming chunks into the correct field (opening vs rebuttal vs cross-exam).
        display_role = role
        if role == "moderator":
            if context.response_type == ResponseType.MODERATOR_INTRO:
                display_role = "moderator_intro"
            elif context.response_type == ResponseType.MODERATOR_SUMMARY:
                display_role = "moderator_summary"
        elif role == "pro":
            if context.response_type == ResponseType.REBUTTAL:
                display_role = "pro-rebuttal"
            elif context.response_type == ResponseType.CROSS_EXAMINE_ASK:
                display_role = "pro-question"
            elif context.response_type == ResponseType.CROSS_EXAMINE_ANSWER:
                display_role = "pro-answer"
            elif context.response_type == ResponseType.USER_ANSWER:
                display_role = "user-answer-pro"
        elif role == "con":
            if context.response_type == ResponseType.REBUTTAL:
                display_role = "con-rebuttal"
            elif context.response_type == ResponseType.CROSS_EXAMINE_ASK:
                display_role = "con-question"
            elif context.response_type == ResponseType.CROSS_EXAMINE_ANSWER:
                display_role = "con-answer"
            elif context.response_type == ResponseType.USER_ANSWER:
                display_role = "user-answer-con"

        agent = self._agent(role)
        self._emit(
            debate_id,
            EventType.AGENT_START,
            role=display_role,
            round_number=round_number,
        )
        full_text = ""
        chunk_count = 0
        t_start = time.perf_counter()
        t_first_chunk = 0.0
        logger.debug("[STREAM_START] role=%s round=%d", display_role, round_number)
        try:
            async for chunk in agent.generate_stream(
                context, response_format=response_format, role=role, max_tokens=max_tokens,
            ):
                if chunk_count == 0:
                    t_first_chunk = time.perf_counter()
                    logger.info(
                        "[TRACE] >>> _stream_agent FIRST_CHUNK role=%s display=%s round=%d ttft=%.3fs <<<",
                        role, display_role, round_number, t_first_chunk - t_start,
                    )
                full_text += chunk
                chunk_count += 1
                if display_role.endswith("-answer") or display_role.endswith("-question"):
                    logger.info(
                        "[XDIAG] CHUNK role=%s display=%s round=%d chunk_num=%d chunk_len=%d chunk_preview=%r",
                        role, display_role, round_number, chunk_count, len(chunk), chunk[:80],
                    )
                if display_role.endswith("-question") or display_role.endswith("-answer"):
                    logger.info(
                        "[XDIAG] SSE_EMIT_CHUNK display_role=%s round=%d content_len=%d content_preview=%r",
                        display_role, round_number, len(chunk), chunk[:80],
                    )
                self._emit(
                    debate_id,
                    EventType.AGENT_CHUNK,
                    role=display_role,
                    round_number=round_number,
                    content=chunk,
                )
        except asyncio.CancelledError:
            raise
        except Exception as stream_err:
            logger.warning(
                "[TRACE] >>> _stream_agent FALLBACK role=%s display=%s round=%d error=%s <<<",
                role, display_role, round_number, stream_err,
            )
            full_text = await agent.generate(context, response_format=response_format, role=role, max_tokens=max_tokens)
            logger.info(
                "[TRACE] >>> _stream_agent FALLBACK_DONE role=%s display=%s round=%d text_len=%d <<<",
                role, display_role, round_number, len(full_text),
            )
            if display_role.endswith("-question") or display_role.endswith("-answer"):
                logger.info(
                    "[XDIAG] SSE_EMIT_FALLBACK display_role=%s round=%d content_len=%d content_preview=%r",
                    display_role, round_number, len(full_text), full_text[:80],
                )
            self._emit(
                debate_id,
                EventType.AGENT_CHUNK,
                role=display_role,
                round_number=round_number,
                content=full_text,
            )

        elapsed = time.perf_counter() - t_start
        self._llm_call_count += 1
        logger.info("[LLM] %s round=%d %.2fs", display_role, round_number, elapsed)
        logger.debug(
            "[STREAM_END] role=%s round=%d chunks=%d elapsed=%.3fs ttft=%.3fs",
            display_role, round_number, chunk_count, elapsed,
            (t_first_chunk - t_start) if t_first_chunk > 0 else 0.0,
        )

        self._emit(
            debate_id,
            EventType.AGENT_DONE,
            role=display_role,
            round_number=round_number,
        )
        if not full_text or not full_text.strip():
            logger.warning(
                "[TRACE] >>> _stream_agent EMPTY role=%s display=%s round=%d chunks=%d response_type=%s <<<",
                role, display_role, round_number, chunk_count,
                context.response_type.value if context.response_type else "unknown",
            )
            # Final safety net: never return empty/whitespace string to the caller.
            # This prevents blank cross-exam questions/answers in the UI.
            response_type_str = context.response_type.value if context.response_type else "default"
            from app.services.llm_service import _fallback_text
            full_text = _fallback_text(response_type_str)
            logger.warning(
                "[TRACE] >>> _stream_agent EMPTY_FALLBACK role=%s display=%s round=%d text=%r <<<",
                role, display_role, round_number, full_text[:80],
            )
            self._emit(
                debate_id,
                EventType.AGENT_CHUNK,
                role=display_role,
                round_number=round_number,
                content=full_text,
            )
        logger.info(
            "[TRACE] >>> _stream_agent RETURN role=%s display=%s round=%d text_len=%d chunks=%d <<<",
            role, display_role, round_number, len(full_text), chunk_count,
        )
        logger.info(
            "[XDIAG] RETURN role=%s display=%s round=%d full_text_len=%d full_text_preview=%r",
            role, display_role, round_number, len(full_text), full_text[:120],
        )
        return full_text

    # ── Public API ────────────────────────────────────────────────

    async def create_debate(
        self,
        topic: str,
        max_rounds: int = 3,
        enable_cross_exam: bool = True,
        enable_moderator: bool = True,
        enable_user_questions: bool = False,
    ) -> Debate:
        debate = Debate(id=str(uuid4()), topic=topic, max_rounds=max_rounds)
        debate._enable_cross_exam = enable_cross_exam  # type: ignore[attr-defined]
        debate._enable_moderator = enable_moderator  # type: ignore[attr-defined]
        debate._enable_user_questions = enable_user_questions  # type: ignore[attr-defined]
        await self._repo.save(debate)
        logger.info(
            "Created debate %s: topic=%r max_rounds=%d cross_exam=%s moderator=%s user_questions=%s",
            debate.id, topic[:60], max_rounds, enable_cross_exam, enable_moderator,
            enable_user_questions,
        )
        return debate

    async def start_debate(self, debate_id: str) -> Debate:
        t_total = time.perf_counter()
        debate = await self._repo.get(debate_id)
        if not debate:
            raise DebateNotFoundError(debate_id)
        if debate.is_completed():
            raise DebateAlreadyRunningError(debate_id)

        self._llm_call_count = 0
        self._llm.start_profiler()
        enable_cross_exam = getattr(debate, "_enable_cross_exam", True)
        enable_moderator = getattr(debate, "_enable_moderator", True)

        logger.info("[DEBATE] start id=%s topic=%r max_rounds=%d cross_exam=%s moderator=%s",
                     debate_id, debate.topic[:60], debate.max_rounds, enable_cross_exam, enable_moderator)

        if debate.status != DebateStatus.IN_PROGRESS:
            debate.advance_status(DebateStatus.IN_PROGRESS)
            t_db = time.perf_counter()
            await self._repo.save(debate)
            logger.debug("[DB] save_debate init %.2fs", time.perf_counter() - t_db)

        self._emit(debate_id, EventType.DEBATE_STARTED, topic=debate.topic, max_rounds=debate.max_rounds,
                   enable_cross_exam=enable_cross_exam, enable_moderator=enable_moderator)

        try:
            for round_num in range(1, debate.max_rounds + 1):
                t_round = time.perf_counter()
                round_focus = get_round_focus(round_num)
                logger.info("[TRACE] >>> start_round debate=%s round=%d focus=%s <<<", debate_id, round_num, round_focus[:40])
                self._emit(debate_id, EventType.ROUND_START, round_number=round_num, round_focus=round_focus)
                round_ = await self._run_round(debate, round_num, enable_cross_exam=enable_cross_exam, enable_moderator=enable_moderator)
                logger.info("[TRACE] >>> add_round debate=%s round=%d <<<", debate_id, round_num)
                debate.add_round(round_)

                t_round_elapsed = time.perf_counter() - t_round
                logger.info("[TRACE] >>> round_done debate=%s round=%d elapsed=%.1fs llm_calls=%d <<<", debate_id, round_num, t_round_elapsed, self._llm_call_count)

                # CRITICAL: Save BEFORE emitting ROUND_DONE, so the frontend
                # can fetch the complete round from the DB.
                logger.info(
                    "[XDIAG] BEFORE_SAVE rounds=%d",
                    len(debate.rounds),
                )
                for rd in debate.rounds:
                    for i, ce in enumerate(rd.cross_examination):
                        logger.info(
                            "[XDIAG] BEFORE_SAVE R%d_CE%d q=%r a=%r",
                            rd.round_number, i, ce.question[:60], ce.answer[:60],
                        )
                if round_num < debate.max_rounds:
                    # CRITICAL: Register the Event BEFORE setting awaiting_input=True
                    # and before emitting AWAITING_INPUT via SSE.
                    # This guarantees the frontend's continue_debate() call can
                    # always find the Event, eliminating the race condition.
                    continue_event = asyncio.Event()
                    self._continue_events[debate_id] = continue_event
                    logger.info("[LIFECYCLE] debate=%s event registered for continue", debate_id)

                    debate.awaiting_input = True
                    t_db = time.perf_counter()
                    logger.info("[TRACE] >>> save_round debate=%s round=%d awaiting_input=True <<<", debate_id, round_num)
                    await self._repo.save(debate)
                    logger.info("[TRACE] >>> save_round_done debate=%s round=%d duration=%.2fs <<<", debate_id, round_num, time.perf_counter() - t_db)

                    # DIAGNOSTIC: verify awaiting_input persisted
                    loaded = await self._repo.get(debate_id)
                    logger.info(
                        "[TRACE] >>> AWAITING_INPUT_DIAG debate=%s local=%s repo=%s local_rounds=%d repo_rounds=%d <<<",
                        debate_id,
                        debate.awaiting_input,
                        loaded.awaiting_input if loaded else "NONE",
                        len(debate.rounds),
                        len(loaded.rounds) if loaded else -1,
                    )
                    if loaded:
                        for rd in loaded.rounds:
                            for i, ce in enumerate(rd.cross_examination):
                                logger.info(
                                    "[XDIAG] AFTER_LOAD R%d_CE%d q=%r a=%r",
                                    rd.round_number, i, ce.question[:60], ce.answer[:60],
                                )

                    # Emit ROUND_DONE AFTER the DB save, so the frontend can
                    # fetch the complete round state.
                    logger.info("[TRACE] >>> emit_round_done debate=%s round=%d <<<", debate_id, round_num)
                    self._emit(debate_id, EventType.ROUND_DONE, round_number=round_num)
                    logger.info("[TRACE] >>> emit_awaiting_input debate=%s round=%d <<<", debate_id, round_num)
                    self._emit(debate_id, EventType.AWAITING_INPUT)
                    logger.info("[LIFECYCLE] debate=%s awaiting_input between rounds %d→%d", debate_id, round_num, round_num + 1)

                    logger.info("[TRACE] >>> awaiting_continue debate=%s round=%d <<<", debate_id, round_num)
                    try:
                        await asyncio.wait_for(continue_event.wait(), timeout=300)
                        logger.info("[TRACE] >>> continue_received debate=%s round=%d <<<", debate_id, round_num)
                    except asyncio.TimeoutError:
                        logger.warning("[TRACE] >>> continue_timeout debate=%s round=%d <<<", debate_id, round_num)
                        try:
                            debate.awaiting_input = False
                            await self._repo.save(debate)
                        except Exception:
                            logger.exception("[LIFECYCLE] debate=%s failed to reset awaiting_input after timeout", debate_id)
                    except asyncio.CancelledError:
                        logger.warning("[LIFECYCLE] debate=%s cancelled while awaiting input round=%d", debate_id, round_num)
                        debate.advance_status(DebateStatus.ERROR)
                        t_db = time.perf_counter()
                        await self._repo.save(debate)
                        logger.debug("[LIFECYCLE] db_save cancel round=%d duration=%.2fs", round_num, time.perf_counter() - t_db)
                        self._continue_events.pop(debate_id, None)
                        self._cleanup_debate(debate_id)
                        return debate
                    finally:
                        self._continue_events.pop(debate_id, None)

                    logger.info("[LIFECYCLE] debate=%s continuing to round %d", debate_id, round_num + 1)
                    debate = await self._repo.get(debate_id)
                    if debate is None:
                        logger.error("[LIFECYCLE] debate=%s disappeared from storage during continue", debate_id)
                        self._cleanup_debate(debate_id)
                        return debate
                else:
                    t_db = time.perf_counter()
                    logger.info("[TRACE] >>> save_round debate=%s round=%d FINAL <<<", debate_id, round_num)
                    await self._repo.save(debate)
                    logger.info("[TRACE] >>> save_round_done debate=%s round=%d FINAL duration=%.2fs <<<", debate_id, round_num, time.perf_counter() - t_db)
                    # Emit ROUND_DONE AFTER the save for the final round too
                    logger.info("[TRACE] >>> emit_round_done debate=%s round=%d FINAL <<<", debate_id, round_num)
                    self._emit(debate_id, EventType.ROUND_DONE, round_number=round_num)

            logger.info("[TRACE] >>> verdict_start debate=%s <<<", debate_id)
            await self._run_verdict(debate)
            logger.info("[TRACE] >>> verdict_done debate=%s <<<", debate_id)
            t_db = time.perf_counter()
            await self._repo.save(debate)
            logger.info("[TRACE] >>> verdict_saved debate=%s duration=%.2fs <<<", debate_id, time.perf_counter() - t_db)
            self._cleanup_debate(debate_id)
        except asyncio.CancelledError:
            logger.warning("[LIFECYCLE] debate=%s cancelled at top level, cleaning up", debate_id)
            debate.advance_status(DebateStatus.ERROR)
            try:
                await self._repo.save(debate)
            except Exception as save_err:
                logger.error("[LIFECYCLE] debate=%s failed to persist ERROR status: %s", debate_id, save_err)
            self._cleanup_debate(debate_id)
            raise
        except Exception:
            logger.exception("[LIFECYCLE] debate=%s failed with exception", debate_id)
            debate.advance_status(DebateStatus.ERROR)
            try:
                t_db = time.perf_counter()
                await self._repo.save(debate)
                logger.debug("[LIFECYCLE] db_save error duration=%.2fs", time.perf_counter() - t_db)
            except Exception as save_err:
                logger.error("[LIFECYCLE] debate=%s failed to persist ERROR status: %s", debate_id, save_err)
            self._cleanup_debate(debate_id)

        total = time.perf_counter() - t_total
        calls_per_round = self._llm_call_count / max(debate.max_rounds, 1)
        logger.info("[DEBATE] completed id=%s total=%.1fs calls=%d avg_per_round=%.1f", debate_id, total, self._llm_call_count, calls_per_round)
        return debate

    async def continue_debate(self, debate_id: str) -> Debate:
        logger.info("[TRACE] >>> HTTP POST /continue debate=%s <<<", debate_id)
        debate = await self._repo.get(debate_id)
        if not debate:
            raise DebateNotFoundError(debate_id)
        logger.info(
            "[XDIAG] CONTINUE_DEBATE debate=%s awaiting_input=%s status=%s rounds=%d",
            debate_id, debate.awaiting_input, debate.status.value, len(debate.rounds),
        )
        if not debate.awaiting_input:
            logger.warning("[TRACE] >>> continue_ignored debate=%s not awaiting_input <<<", debate_id)
            return debate
        debate.awaiting_input = False
        t_db = time.perf_counter()
        await self._repo.save(debate)
        logger.info("[TRACE] >>> continue_saved debate=%s <<<", debate_id)
        logger.info(
            "[XDIAG] CONTINUE_DEBATE SAVED debate=%s awaiting_input=False",
            debate_id,
        )
        # Signal the waiting Event
        event = self._continue_events.pop(debate_id, None)
        if event is not None:
            event.set()
            logger.info("[TRACE] >>> continue_event_set debate=%s <<<", debate_id)
        else:
            logger.warning("[TRACE] >>> continue_event_missing debate=%s <<<", debate_id)
        return debate

    async def get_debate(self, debate_id: str) -> Debate | None:
        return await self._repo.get(debate_id)

    async def save_debate(self, debate: Debate) -> None:
        await self._repo.save(debate)

    async def submit_questions(
        self,
        debate_id: str,
        pro_question: str = "",
        con_question: str = "",
    ) -> Debate:
        """Submit optional user questions during a debate pause.

        Generates answers from the respective agents and stores them
        as UserQuestionQA on the current (latest) round.
        If the debate is not awaiting input, or there are no questions,
        this is a no-op.
        """
        debate = await self._repo.get(debate_id)
        if not debate:
            raise DebateNotFoundError(debate_id)
        if not debate.awaiting_input:
            logger.warning("[QUESTIONS] debate=%s not awaiting_input, ignoring", debate_id)
            return debate

        current_round = debate.latest_round()
        if not current_round:
            logger.warning("[QUESTIONS] debate=%s no rounds yet, ignoring", debate_id)
            return debate

        if not pro_question.strip() and not con_question.strip():
            return debate

        language = detect_language(debate.topic)
        res_pro_stance, res_con_stance = self._resolve_stance(debate.topic)
        round_num = current_round.round_number

        if pro_question.strip():
            pro_ctx = AgentContext(
                topic=debate.topic,
                round_number=round_num,
                response_type=ResponseType.USER_ANSWER,
                previous_rounds=debate.rounds,
                debate_id=debate.id,
                language=language,
                stance=res_pro_stance,
                opponent_name=res_con_stance or "the opposing side",
                role="pro",
                cross_target=pro_question.strip(),
            )
            pro_answer = await self._stream_agent(
                "pro", pro_ctx, debate.id, round_num,
                max_tokens=self._resolve_max_tokens(ResponseType.USER_ANSWER),
            )
            current_round.user_questions.append(
                UserQuestionQA(target_role=AgentRole.PRO, question=pro_question.strip(), answer=pro_answer)
            )

        if con_question.strip():
            con_ctx = AgentContext(
                topic=debate.topic,
                round_number=round_num,
                response_type=ResponseType.USER_ANSWER,
                previous_rounds=debate.rounds,
                debate_id=debate.id,
                language=language,
                stance=res_con_stance,
                opponent_name=res_pro_stance or "the proposing side",
                role="con",
                cross_target=con_question.strip(),
            )
            con_answer = await self._stream_agent(
                "con", con_ctx, debate.id, round_num,
                max_tokens=self._resolve_max_tokens(ResponseType.USER_ANSWER),
            )
            current_round.user_questions.append(
                UserQuestionQA(target_role=AgentRole.CON, question=con_question.strip(), answer=con_answer)
            )

        await self._repo.save(debate)
        logger.info(
            "[QUESTIONS] debate=%s round=%d pro_q=%s con_q=%s user_questions=%d",
            debate_id, round_num,
            bool(pro_question.strip()), bool(con_question.strip()),
            len(current_round.user_questions),
        )
        return debate


    # ── Stance resolution ──────────────────────────────────────────

    @staticmethod
    def _extract_evidence(text: str) -> list:
        """Delegate to prompts.extract_evidence. Retained for test compatibility."""
        from app.prompts.base import extract_evidence as _do
        return _do(text)

    @staticmethod
    def _parse_judge_response(content: str) -> dict[str, object]:
        """Delegate to prompts.parse_judge_response. Retained for test compatibility."""
        from app.prompts.base import parse_judge_response as _do
        return _do(content)

    @staticmethod
    def _resolve_stance(topic: str) -> tuple[str | None, str | None]:
        """Determine each agent's concrete stance from the debate topic.

        Returns (pro_stance, con_stance):
          pro_stance: what the Pro agent should argue FOR
          con_stance: what the Con agent should argue FOR

        For yes/no questions both return None (default yes/no framing).
        For binary choices (A vs B, Should X or Y, A or B) Pro=first, Con=second.
        """
        t = topic.strip()

        # "Should A or B?" — Pro=first, Con=second
        # Extract the last meaningful noun-phrase before "or" as option A,
        # and the first noun-phrase after "or" as option B.
        for prefix in ("should i ", "should we ", "should ", "Should I ", "Should we ", "Should "):
            if t.startswith(prefix):
                for sep in (" or ", " or, "):
                    if sep in t:
                        parts = t.split(sep, 1)
                        if len(parts) == 2:
                            before = parts[0]
                            for pfx in ("should i ", "should we ", "should ",
                                        "Should I ", "Should we ", "Should "):
                                before = before.removeprefix(pfx)
                            # Take the LAST noun-like word(s) before "or" as option A.
                            # Skip leading verbs ("eat KFC" → "KFC", "buy a house" → "a house")
                            words = before.strip().split()
                            if len(words) == 1:
                                a = words[0]
                            elif len(words) == 2 and len(words[0]) <= 4:
                                # Likely verb + noun: "eat KFC", "buy Apple"
                                a = words[-1]
                            else:
                                a = " ".join(words[-2:]).strip(", ")
                            a = a.rstrip(",.?!").strip()
                            # Take the first 1-2 words after "or". Drop trailing context.
                            # "McDonald's on Thursday" → "McDonald's"
                            # "rent an apartment" → "rent an apartment"
                            b_raw = parts[1].strip().rstrip("?").strip(",.?! ").strip()
                            b_words = b_raw.split()
                            if len(b_words) >= 2 and len(b_words[0]) <= 4:
                                # Short first word likely a verb/preposition → include next
                                b = " ".join(b_words[:2])
                            else:
                                b = b_words[0]
                            if a and b and a.lower() != b.lower():
                                return (a, b)
                break

        # "A 还是 B" — Chinese binary choice ("星期四应该吃肯德基还是麦当劳")
        # Pro=first option, Con=second option.
        # Chinese has no word-boundary spaces, so we use character-level heuristics
        # to extract the entity names from before/after the "还是" separator.
        if "还是" in t:
            parts = t.split("还是", 1)
            if len(parts) == 2:
                before = parts[0].strip()
                after = parts[1].strip().rstrip("？?.,!！。，；;")
                import re
                # Extract option A: find the last contiguous Chinese block,
                # then narrow to the entity name.
                #   "星期四应该吃肯德基"  →  "肯德基"
                #   "买阿里巴巴"         →  strip leading verb  →  "阿里巴巴"
                #   "我要苹果"           →  strip verb "要"   →  "苹果"
                SINGLE_VERBS = "去来吃喝买卖用做打看听玩学修改换选开关读写要"
                blocks = re.findall(r'[一-鿿]+', before)
                if blocks:
                    last_block = blocks[-1]
                    if len(last_block) == 2:
                        # 2-char concept like "买房": keep the whole thing
                        a = last_block
                    elif last_block[0] in SINGLE_VERBS:
                        a = last_block[1:]  # "买阿里巴巴"  →  "阿里巴巴"
                    else:
                        # Try last 3 chars; if starts with verb, try last 2
                        c3 = last_block[-3:]
                        if c3[0] in SINGLE_VERBS and len(last_block) >= 4:
                            c2 = last_block[-2:]
                            a = c2[1:] if c2[0] in SINGLE_VERBS else c2
                        else:
                            a = c3
                            if len(a) > 1 and a[0] in SINGLE_VERBS:
                                a = a[1:]  # "选华为"  →  "华为"
                else:
                    # No Chinese chars in "before" — apply English verb stripping
                    # "eat KFC" → "KFC", "buy Apple" → "Apple"
                    words = before.strip().split()
                    if len(words) >= 2 and len(words[0]) <= 4:
                        a = words[-1]
                    else:
                        a = before
                # Extract option B: first Chinese entity after "还是".
                # If after still contains "还是" (3+ options), split on first one.
                if "还是" in after:
                    after = after.split("还是")[0]
                match = re.search(r'[一-鿿]{2,}', after)
                b = match.group(0) if match else after
                if a and b:
                    return (a, b)

        # "A vs B" / "A versus B"
        for sep in (" vs ", " versus ", " vs. "):
            if sep in t:
                parts = t.split(sep, 1)
                if len(parts) == 2:
                    a = parts[0].strip()
                    b = parts[1].strip().rstrip("?").strip()
                    if a and b:
                        return (a, b)
                break

        # "A or B" (no should prefix, e.g. "KFC or McDonald's?")
        for sep in (" or ", " or, "):
            if sep in t:
                parts = t.split(sep, 1)
                if len(parts) == 2:
                    a = parts[0].strip().rstrip(",").strip()
                    b = parts[1].strip().rstrip("?").strip()
                    if a and b and a.lower() != b.lower():
                        return (a, b)

        # Default: yes/no mode — Pro=affirmative, Con=negative
        return (None, None)

    def _agent(self, role: str) -> BaseAgent:
        cls = AgentRegistry.get(role)
        model = self._resolve_model(role)
        return cls(self._llm, model_name=model)

    def _cleanup_debate(self, debate_id: str) -> None:
        """Clean up resources associated with a debate."""
        logger.info("[TRACE] >>> cleanup_start debate=%s <<<", debate_id)
        self._continue_events.pop(debate_id, None)
        get_event_queue_registry().close(debate_id)
        logger.info("[TRACE] >>> cleanup_done debate=%s <<<", debate_id)

    # ── Event-based wait (replaces sleep-loop polling) ───────────

    async def _wait_for_continue(self, debate_id: str) -> None:
        """Deprecated: continue logic is now inlined in start_debate().
        
        Kept for backward compatibility with tests.
        """
        event = asyncio.Event()
        self._continue_events[debate_id] = event
        try:
            await asyncio.wait_for(event.wait(), timeout=300)
        except asyncio.TimeoutError:
            pass
        finally:
            self._continue_events.pop(debate_id, None)

    # ── Gather helper ────────────────────────────────────────────

    @staticmethod
    async def _gather_tasks(*tasks: asyncio.Task[str]) -> list[str]:
        """Gather tasks with return_exceptions=True, re-raise on failure.

        Returns the list of results if all tasks succeed.
        Logs and re-raises the first exception found.
        Cancels remaining tasks on failure to avoid orphaned work.
        """
        results = await asyncio.gather(*tasks, return_exceptions=True)
        failures: list[tuple[int, BaseException]] = []
        for i, result in enumerate(results):
            if isinstance(result, BaseException):
                failures.append((i, result))
        if failures:
            for i, exc in failures:
                logger.error("[GATHER] task %d/%d failed: %s: %s", i, len(tasks), type(exc).__name__, exc)
            # Cancel any still-running tasks
            for task in tasks:
                if not task.done():
                    task.cancel()
            raise failures[0][1]
        logger.debug("[GATHER] all %d tasks completed successfully", len(tasks))
        return results  # type: ignore[return-value]

    # ── Round execution (parallel-optimised) ─────────────────────

    async def _run_round(
        self,
        debate: Debate,
        round_num: int,
        enable_cross_exam: bool = True,
        enable_moderator: bool = True,
    ) -> Round:
        """Execute a single debate round with maximal parallelisation.

        Dependency analysis:
        - moderator_intro: needs only topic + round_focus + history
        - pro_opening: needs only topic + round_focus + history
        - con_opening: needs only topic + round_focus + history
        → All three are INDEPENDENT → Stage 1 parallel

        - pro_ask: needs topic + round_focus + history (independent of con_ask)
        - con_ask: needs topic + round_focus + history (independent of pro_ask)
        - pro_rebuttal: needs only con_opening_text (available after Stage 1)
        - con_rebuttal: needs only pro_opening_text (available after Stage 1)
        → All four are INDEPENDENT → Stage 2 parallel

        - con_answer: needs pro_question (available after Stage 2)
        - pro_answer: needs con_question (available after Stage 2)
        → Both are INDEPENDENT → Stage 3 parallel

        - moderator_summary: needs all of the above → Stage 4 serial
        """
        language = detect_language(debate.topic)
        round_focus = get_round_focus(round_num)
        round_ = Round(round_number=round_num, round_focus=round_focus)
        res_pro_stance, res_con_stance = self._resolve_stance(debate.topic)
        trace_r1 = f"R{round_num}_PRO_TO_CON"
        trace_r2 = f"R{round_num}_CON_TO_PRO"
        logger.info("[XDIAG] TRACE_ID %s START", trace_r1)
        logger.info("[XDIAG] TRACE_ID %s START", trace_r2)

        # ── Stage 1: moderator_intro + pro_opening + con_opening (parallel) ──
        stage1_tasks: dict[str, asyncio.Task[str]] = {}

        if enable_moderator:
            mod_intro_ctx = AgentContext(
                topic=debate.topic, round_number=round_num, round_focus=round_focus,
                response_type=ResponseType.MODERATOR_INTRO,
                previous_rounds=debate.rounds, debate_id=debate.id, language=language,
            )
            stage1_tasks["moderator_intro"] = asyncio.create_task(
                self._stream_agent("moderator", mod_intro_ctx, debate.id, round_num,
                                   max_tokens=self._resolve_max_tokens(ResponseType.MODERATOR_INTRO))
            )

        pro_opening_ctx = AgentContext(
            topic=debate.topic, round_number=round_num, round_focus=round_focus,
            response_type=ResponseType.OPENING,
            previous_rounds=debate.rounds, debate_id=debate.id, language=language,
            stance=res_pro_stance, opponent_name=res_con_stance or "the opposing side",
        )
        stage1_tasks["pro_opening"] = asyncio.create_task(
            self._stream_agent("pro", pro_opening_ctx, debate.id, round_num,
                               max_tokens=self._resolve_max_tokens(ResponseType.OPENING))
        )

        con_opening_ctx = AgentContext(
            topic=debate.topic, round_number=round_num, round_focus=round_focus,
            response_type=ResponseType.OPENING,
            previous_rounds=debate.rounds, debate_id=debate.id, language=language,
            stance=res_con_stance, opponent_name=res_pro_stance or "the proposing side",
        )
        stage1_tasks["con_opening"] = asyncio.create_task(
            self._stream_agent("con", con_opening_ctx, debate.id, round_num,
                               max_tokens=self._resolve_max_tokens(ResponseType.OPENING))
        )

        logger.info("[STAGE] debate=%s round=%d stage=1 starting tasks=%s", debate.id, round_num, list(stage1_tasks.keys()))
        s1_results = await self._gather_tasks(*stage1_tasks.values())
        logger.info("[STAGE] debate=%s round=%d stage=1 completed", debate.id, round_num)
        s1: dict[str, str] = dict(zip(stage1_tasks.keys(), s1_results))

        mod_intro_text = s1.get("moderator_intro")
        pro_opening_text = s1["pro_opening"]
        con_opening_text = s1["con_opening"]

        if mod_intro_text is not None:
            round_.moderator_intro = mod_intro_text
        round_.pro_opening = Argument(role=AgentRole.PRO, content=pro_opening_text)
        round_.con_opening = Argument(role=AgentRole.CON, content=con_opening_text)
        round_.pro_opening.evidence = self._extract_evidence(pro_opening_text)
        round_.con_opening.evidence = self._extract_evidence(con_opening_text)

        # ── Stage 2: cross-exam asks + rebuttals (parallel) ──
        stage2_tasks: dict[str, asyncio.Task[str]] = {}

        if enable_cross_exam:
            pro_ask_ctx = AgentContext(
                topic=debate.topic, round_number=round_num, round_focus=round_focus,
                response_type=ResponseType.CROSS_EXAMINE_ASK,
                previous_rounds=debate.rounds, debate_id=debate.id, language=language,
                stance=res_pro_stance, opponent_name=res_con_stance or "the opposing side",
                role="pro",
            )
            stage2_tasks["pro_ask"] = asyncio.create_task(
                self._stream_agent("pro", pro_ask_ctx, debate.id, round_num,
                                   max_tokens=self._resolve_max_tokens(ResponseType.CROSS_EXAMINE_ASK))
            )
            con_ask_ctx = AgentContext(
                topic=debate.topic, round_number=round_num, round_focus=round_focus,
                response_type=ResponseType.CROSS_EXAMINE_ASK,
                previous_rounds=debate.rounds, debate_id=debate.id, language=language,
                stance=res_con_stance, opponent_name=res_pro_stance or "the proposing side",
                role="con",
            )
            stage2_tasks["con_ask"] = asyncio.create_task(
                self._stream_agent("con", con_ask_ctx, debate.id, round_num,
                                   max_tokens=self._resolve_max_tokens(ResponseType.CROSS_EXAMINE_ASK))
            )

        pro_rebuttal_ctx = AgentContext(
            topic=debate.topic, round_number=round_num, round_focus=round_focus,
            response_type=ResponseType.REBUTTAL,
            previous_rounds=debate.rounds, debate_id=debate.id, language=language,
            stance=res_pro_stance, opponent_name=res_con_stance or "the opposing side",
            role="pro",
            latest_opponent=con_opening_text[:500],
        )
        stage2_tasks["pro_rebuttal"] = asyncio.create_task(
            self._stream_agent("pro", pro_rebuttal_ctx, debate.id, round_num,
                               max_tokens=self._resolve_max_tokens(ResponseType.REBUTTAL))
        )

        con_rebuttal_ctx = AgentContext(
            topic=debate.topic, round_number=round_num, round_focus=round_focus,
            response_type=ResponseType.REBUTTAL,
            previous_rounds=debate.rounds, debate_id=debate.id, language=language,
            stance=res_con_stance, opponent_name=res_pro_stance or "the proposing side",
            role="con",
            latest_opponent=pro_opening_text[:500],
        )
        stage2_tasks["con_rebuttal"] = asyncio.create_task(
            self._stream_agent("con", con_rebuttal_ctx, debate.id, round_num,
                               max_tokens=self._resolve_max_tokens(ResponseType.REBUTTAL))
        )

        logger.info("[STAGE] debate=%s round=%d stage=2 starting tasks=%s", debate.id, round_num, list(stage2_tasks.keys()))
        s2_results = await self._gather_tasks(*stage2_tasks.values())
        logger.info("[STAGE] debate=%s round=%d stage=2 completed", debate.id, round_num)
        s2: dict[str, str] = dict(zip(stage2_tasks.keys(), s2_results))

        pro_question = s2.get("pro_ask", "")
        con_question = s2.get("con_ask", "")
        pro_rebuttal_text = s2["pro_rebuttal"]
        con_rebuttal_text = s2["con_rebuttal"]
        logger.info(
            "[TRACE] >>> stage2 ASSIGN pro_question_len=%d con_question_len=%d pro_rebuttal_len=%d con_rebuttal_len=%d <<<",
            len(pro_question), len(con_question), len(pro_rebuttal_text), len(con_rebuttal_text),
        )

        round_.pro_rebuttal = Argument(role=AgentRole.PRO, content=pro_rebuttal_text)
        round_.con_rebuttal = Argument(role=AgentRole.CON, content=con_rebuttal_text)
        round_.pro_rebuttal.evidence = self._extract_evidence(pro_rebuttal_text)
        round_.con_rebuttal.evidence = self._extract_evidence(con_rebuttal_text)

        # ── Stage 3: cross-exam answers (parallel) ──
        if enable_cross_exam:
            con_answer_ctx = AgentContext(
                topic=debate.topic, round_number=round_num, round_focus=round_focus,
                response_type=ResponseType.CROSS_EXAMINE_ANSWER,
                previous_rounds=debate.rounds, debate_id=debate.id, language=language,
                stance=res_con_stance, opponent_name=res_pro_stance or "the proposing side",
                role="con",
                cross_target=pro_question,
            )
            pro_answer_ctx = AgentContext(
                topic=debate.topic, round_number=round_num, round_focus=round_focus,
                response_type=ResponseType.CROSS_EXAMINE_ANSWER,
                previous_rounds=debate.rounds, debate_id=debate.id, language=language,
                stance=res_pro_stance, opponent_name=res_con_stance or "the opposing side",
                role="pro",
                cross_target=con_question,
            )

            logger.info("[STAGE] debate=%s round=%d stage=3 starting cross-exam answers", debate.id, round_num)
            s3_results = await self._gather_tasks(
                asyncio.create_task(
                    self._stream_agent("con", con_answer_ctx, debate.id, round_num,
                                       max_tokens=self._resolve_max_tokens(ResponseType.CROSS_EXAMINE_ANSWER))
                ),
                asyncio.create_task(
                    self._stream_agent("pro", pro_answer_ctx, debate.id, round_num,
                                       max_tokens=self._resolve_max_tokens(ResponseType.CROSS_EXAMINE_ANSWER))
                ),
            )
            con_answer, pro_answer = s3_results[0], s3_results[1]
            logger.info(
                "[XDIAG] STAGE3_ANSWER %s question_len=%d answer_len=%d answer_preview=%r",
                trace_r1, len(pro_question), len(con_answer), con_answer[:80],
            )
            logger.info(
                "[XDIAG] STAGE3_ANSWER %s question_len=%d answer_len=%d answer_preview=%r",
                trace_r2, len(con_question), len(pro_answer), pro_answer[:80],
            )
            logger.info(
                "[TRACE] >>> stage3 ASSIGN con_answer_len=%d pro_answer_len=%d <<<",
                len(con_answer), len(pro_answer),
            )
            logger.info(
                "[XDIAG] STAGE3_RESULT con_answer=%r pro_answer=%r",
                con_answer[:120], pro_answer[:120],
            )
            logger.info("[STAGE] debate=%s round=%d stage=3 completed", debate.id, round_num)

            logger.info(
                "[XDIAG] BEFORE_STORE %s question=%r answer=%r",
                trace_r1, pro_question[:80], con_answer[:80],
            )
            logger.info(
                "[XDIAG] BEFORE_STORE %s question=%r answer=%r",
                trace_r2, con_question[:80], pro_answer[:80],
            )
            # Final guard: ensure no empty cross-exam fields are persisted.
            from app.services.llm_service import _fallback_text
            if not pro_question or not pro_question.strip():
                logger.warning("[XDIAG] FALLBACK_FILL pro_question was empty/whitespace")
                pro_question = _fallback_text("cross_examine_ask")
            if not con_question or not con_question.strip():
                logger.warning("[XDIAG] FALLBACK_FILL con_question was empty/whitespace")
                con_question = _fallback_text("cross_examine_ask")
            if not con_answer or not con_answer.strip():
                logger.warning("[XDIAG] FALLBACK_FILL con_answer was empty/whitespace")
                con_answer = _fallback_text("cross_examine_answer")
            if not pro_answer or not pro_answer.strip():
                logger.warning("[XDIAG] FALLBACK_FILL pro_answer was empty/whitespace")
                pro_answer = _fallback_text("cross_examine_answer")
            qa1 = CrossExaminationQA(question_role=AgentRole.PRO, question=pro_question, answer_role=AgentRole.CON, answer=con_answer)
            qa2 = CrossExaminationQA(question_role=AgentRole.CON, question=con_question, answer_role=AgentRole.PRO, answer=pro_answer)
            # Absolute last check right before append
            if not qa1.answer or not qa1.answer.strip():
                qa1.answer = _fallback_text("cross_examine_answer")
            if not qa2.answer or not qa2.answer.strip():
                qa2.answer = _fallback_text("cross_examine_answer")
            round_.cross_examination.append(qa1)
            round_.cross_examination.append(qa2)
            logger.info(
                "[XDIAG] AFTER_STORE %s stored_q=%r stored_a=%r",
                trace_r1,
                round_.cross_examination[0].question[:80],
                round_.cross_examination[0].answer[:80],
            )
            logger.info(
                "[XDIAG] AFTER_STORE %s stored_q=%r stored_a=%r",
                trace_r2,
                round_.cross_examination[1].question[:80] if len(round_.cross_examination) > 1 else "NONE",
                round_.cross_examination[1].answer[:80] if len(round_.cross_examination) > 1 else "NONE",
            )

        # ── Stage 4: moderator summary (serial) ──
        if enable_moderator:
            mod_summary_ctx = AgentContext(
                topic=debate.topic, round_number=round_num, round_focus=round_focus,
                response_type=ResponseType.MODERATOR_SUMMARY,
                previous_rounds=list(debate.rounds) + [round_],
                debate_id=debate.id, language=language,
            )
            logger.info("[STAGE] debate=%s round=%d stage=4 starting moderator summary", debate.id, round_num)
            mod_summary = await self._stream_agent(
                "moderator", mod_summary_ctx, debate.id, round_num,
                max_tokens=self._resolve_max_tokens(ResponseType.MODERATOR_SUMMARY),
            )
            round_.moderator_summary = mod_summary
            logger.info(
                "[TRACE] >>> stage4 ASSIGN moderator_summary_len=%d <<<",
                len(mod_summary),
            )
            # Store the full summary as the steer — the moderator already
            # includes forward guidance in its MODERATOR_SUMMARY response.
            round_.moderator_steer = (
                f"Round {round_num} focus: {round_focus}. "
                f"Moderator guidance: {mod_summary}"
            )
            # Generate compact round memory for context window management
            round_.memory = RoundMemory.from_moderator_summary(mod_summary)
            logger.info("[STAGE] debate=%s round=%d stage=4 completed", debate.id, round_num)

        return round_

    async def _run_verdict(self, debate: Debate) -> None:
        language = detect_language(debate.topic)
        judge_ctx = AgentContext(
            topic=debate.topic, round_number=debate.max_rounds + 1,
            response_type=ResponseType.VERDICT,
            previous_rounds=debate.rounds, debate_id=debate.id, language=language,
            role="judge",
        )
        logger.info("[TRACE] >>> verdict_emit_start debate=%s <<<", debate.id)
        self._emit(debate.id, EventType.VERDICT_START)
        content = await self._stream_agent(
            "judge", judge_ctx, debate.id, debate.max_rounds + 1,
            response_format={"type": "json_object"}, max_tokens=settings.JUDGE_MAX_TOKENS,
        )
        logger.info("[TRACE] >>> verdict_emit_done debate=%s <<<", debate.id)
        self._emit(debate.id, EventType.VERDICT_DONE)
        parsed = self._parse_judge_response(content)
        evaluation = None
        if parsed.get("winner") or parsed.get("scores"):
            from app.domain.debate import JudgeEvaluation
            evaluation = JudgeEvaluation.from_dict(parsed)  # type: ignore[arg-type]
        verdict = Verdict(
            summary=str(parsed.get("summary", "")),
            recommendation=str(parsed.get("recommendation", "")),
            evaluation=evaluation,
        )
        debate.set_verdict(verdict)

