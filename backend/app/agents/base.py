"""Abstract base class for all debate agents."""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any

import logging

from app.domain.enums import ResponseType
from app.services.llm_service import LLMService


def detect_language(text: str) -> str:
    if not text:
        return "English"
    hiragana_katakana = sum(1 for c in text if "\u3040" <= c <= "\u309f" or "\u30a0" <= c <= "\u30ff")
    hangul = sum(1 for c in text if "\uac00" <= c <= "\ud7af")
    cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff" or "\u3400" <= c <= "\u4dbf")
    if hiragana_katakana > 0:
        return "Japanese"
    if hangul > 0:
        return "Korean"
    if cjk > 3:
        return "Chinese"
    return "English"


class AgentContext:
    """Single source of truth for every prompt sent to an LLM agent.

    All prompt construction reads from this context; nothing else.
    """

    def __init__(
        self,
        topic: str,
        round_number: int,
        *,
        role: str = "",
        round_focus: str | None = None,
        response_type: ResponseType = ResponseType.OPENING,
        previous_rounds: list[Any] | None = None,
        moderator_steer: str | None = None,
        latest_opponent: str | None = None,
        cross_target: str | None = None,
        debate_id: str | None = None,
        language: str = "English",
        stance: str | None = None,
        opponent_name: str = "The Opposition",
    ) -> None:
        self.topic = topic
        self.round_number = round_number
        self.role = role
        self.round_focus = round_focus
        self.response_type = response_type
        self.previous_rounds = previous_rounds or []
        self.moderator_steer = moderator_steer
        self.latest_opponent = latest_opponent
        self.cross_target = cross_target
        self.debate_id = debate_id
        self.language = language
        self.stance = stance
        self.opponent_name = opponent_name


class BaseAgent(ABC):
    """Base class for all debate agents.

    Subclasses define SYSTEM_PROMPT. The PromptBuilder handles all
    prompt construction from AgentContext.
    """

    SYSTEM_PROMPT: str = ""

    def __init__(self, llm_service: LLMService, model_name: str | None = None) -> None:
        self._llm = llm_service
        self._model_name = model_name

    def build_prompt(self, context: AgentContext) -> str:
        """Build user prompt string via PromptBuilder (single pipeline)."""
        from app.prompts.base import PromptBuilder
        from app.agents.registry import AgentRegistry

        # Auto-detect role from registry if not already set on context
        if not context.role:
            detected = AgentRegistry.get_role_for_agent(type(self))
            if detected:
                context.role = detected

        return PromptBuilder.build(context)["user_prompt"]

    async def generate(
        self, context: AgentContext, response_format: dict[str, str] | None = None,
        role: str = "", max_tokens: int | None = None,
    ) -> str:
        effective_role = role or context.role or "unknown"
        built_user = self.build_prompt(context)
        built_sys = self.SYSTEM_PROMPT

        logger = logging.getLogger("app.agents.base")
        logger.info(
            "[PROMPT] role=%s round=%d response_type=%s prompt_len=%d model=%s max_tokens=%s",
            effective_role, context.round_number,
            context.response_type.value if hasattr(context.response_type, "value") else context.response_type,
            len(built_user), self._model_name, max_tokens,
        )
        logger.debug("[PROMPT_DETAIL] %s", built_user[:2000])

        kwargs: dict[str, object] = {
            "prompt": built_user,
            "system_prompt": built_sys,
            "model": self._model_name,
            "role": effective_role,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        return await self._llm.generate(**kwargs)  # type: ignore[arg-type]

    async def generate_stream(
        self,
        context: AgentContext,
        response_format: dict[str, str] | None = None,
        role: str = "",
        max_tokens: int | None = None,
    ) -> "AsyncGenerator[str, None]":
        effective_role = role or context.role or "unknown"
        built_user = self.build_prompt(context)
        built_sys = self.SYSTEM_PROMPT

        logger = logging.getLogger("app.agents.base")
        logger.info(
            "[PROMPT] role=%s round=%d response_type=%s prompt_len=%d model=%s max_tokens=%s",
            effective_role, context.round_number,
            context.response_type.value if hasattr(context.response_type, "value") else context.response_type,
            len(built_user), self._model_name, max_tokens,
        )
        logger.debug("[PROMPT_DETAIL] %s", built_user[:2000])

        kwargs: dict[str, object] = {
            "prompt": built_user,
            "system_prompt": built_sys,
            "model": self._model_name,
            "role": effective_role,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        async for chunk in self._llm.generate_stream(**kwargs):  # type: ignore[arg-type]
            yield chunk


def _safe_str(val: Any) -> str:
    """Convert any value to a string, handling enums."""
    if val is None:
        return ""
    if hasattr(val, "value"):
        return str(val.value)
    return str(val)


def _format_round_compact(r: Any) -> str:
    focus = getattr(r, "round_focus", "") or ""
    summary = getattr(r, "moderator_summary", "") or ""
    pro = getattr(r, "pro_opening", None)
    con = getattr(r, "con_opening", None)
    pro_text = getattr(pro, "content", "")[:80] if pro else ""
    con_text = getattr(con, "content", "")[:80] if con else ""
    return f"R{getattr(r, 'round_number', '?')}: {focus[:60]}. Pro: {pro_text}... Con: {con_text}... Summary: {summary[:100]}"


def _format_round_full(r: Any) -> str:
    parts = [f"=== Round {getattr(r, 'round_number', '?')} ==="]
    focus = getattr(r, "round_focus", "")
    if focus:
        parts.append(f"Focus: {focus}")
    intro = getattr(r, "moderator_intro", "")
    if intro:
        parts.append(f"Moderator: {intro[:300]}")
    pro = getattr(r, "pro_opening", None)
    if pro and getattr(pro, "content", None):
        parts.append(f"Pro: {pro.content[:500]}")
    con = getattr(r, "con_opening", None)
    if con and getattr(con, "content", None):
        parts.append(f"Con: {con.content[:500]}")
    cross = getattr(r, "cross_examination", [])
    for qa in cross:
        q_role = getattr(qa, "question_role", None)
        q_role_str = _safe_str(q_role)
        q_text = getattr(qa, "question", "")[:200]
        parts.append(f"Q({q_role_str}): {q_text}")
        a_role = getattr(qa, "answer_role", None)
        a_role_str = _safe_str(a_role)
        a_text = getattr(qa, "answer", "")[:200]
        parts.append(f"A({a_role_str}): {a_text}")
    p_reb = getattr(r, "pro_rebuttal", None)
    if p_reb and getattr(p_reb, "content", None):
        parts.append(f"Pro rebuttal: {p_reb.content[:300]}")
    c_reb = getattr(r, "con_rebuttal", None)
    if c_reb and getattr(c_reb, "content", None):
        parts.append(f"Con rebuttal: {c_reb.content[:300]}")
    summary = getattr(r, "moderator_summary", "")
    if summary:
        parts.append(f"Summary: {summary[:300]}")
    return "\n".join(parts)
