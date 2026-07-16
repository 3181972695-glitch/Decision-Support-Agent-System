"""PromptBuilder — single pipeline for constructing all LLM prompts.

Every prompt in the system goes through PromptBuilder.build(context).
No other code concatenates prompt strings.

Architecture:
  AgentContext (single source of truth)
       ↓
  PromptBuilder.build(context)
       ↓  returns {"system_prompt": str, "user_prompt": str}
  LLMService.generate(prompt=user_prompt, system_prompt=system_prompt)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.domain.enums import ResponseType

if TYPE_CHECKING:
    from app.agents.base import AgentContext

logger = logging.getLogger("app.prompts")

DEBUG_PROMPTS = False


def _safe_str(val: Any) -> str:
    if val is None:
        return ""
    if hasattr(val, "value"):
        return str(val.value)
    return str(val)


def format_history(previous_rounds: list[Any], max_chars: int = 1500) -> str:
    """Format previous rounds as compact context.

    The latest round gets full text; earlier rounds get 1-line summaries.
    """
    if not previous_rounds:
        return ""

    parts: list[str] = []
    total = 0
    n = len(previous_rounds)

    for i, r in enumerate(previous_rounds):
        is_last = i == n - 1
        if is_last:
            text = _format_round_full(r)
        else:
            text = _format_round_compact(r)

        if total + len(text) > max_chars:
            parts.append(text[: max_chars - total] + "...")
            break
        parts.append(text)
        total += len(text)

    return "\n\n".join(parts)


def _format_round_compact(r: Any) -> str:
    focus = getattr(r, "round_focus", "") or ""
    summary = getattr(r, "moderator_summary", "") or ""
    pro = getattr(r, "pro_opening", None)
    con = getattr(r, "con_opening", None)
    pro_text = getattr(pro, "content", "")[:80] if pro else ""
    con_text = getattr(con, "content", "")[:80] if con else ""
    return (
        f"R{getattr(r, 'round_number', '?')}: {focus[:60]}. "
        f"Pro: {pro_text}... Con: {con_text}... Summary: {summary[:100]}"
    )


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


_ROUTE_MARKERS = {
    ResponseType.MODERATOR_INTRO: "[ROUTE:MODERATOR_INTRO Round introduction]",
    ResponseType.MODERATOR_SUMMARY: "[ROUTE:MODERATOR_SUMMARY Round summary]",
    ResponseType.USER_ANSWER: "[ROUTE:USER_ANSWER]",
}


class PromptBuilder:
    """Single entry point for constructing every prompt sent to the LLM.

    Usage:
        built = PromptBuilder.build(context)
        llm.generate(prompt=built["user_prompt"],
                      system_prompt=built["system_prompt"])
    """

    @classmethod
    def build(cls, context: AgentContext) -> dict[str, str]:
        """Build the full prompt for any agent role and response type.

        Returns {"system_prompt": str, "user_prompt": str}.
        System prompt is resolved from the template module for the agent's role.
        """
        system_prompt = cls._resolve_system_prompt(context)
        user_prompt = cls._build_user_prompt(context)

        if DEBUG_PROMPTS:
            role = context.role or "unknown"
            rtype = context.response_type.value if hasattr(context.response_type, "value") else str(context.response_type)
            model = getattr(context, "_model_name", "default")
            logger.info(
                "\n========== FINAL PROMPT ==========\n"
                "Role: %s\nResponse type: %s\nModel: %s\n"
                "--- System prompt ---\n%s\n"
                "--- User prompt ---\n%s\n"
                "==================================",
                role, rtype, model, system_prompt, user_prompt,
            )

        return {"system_prompt": system_prompt, "user_prompt": user_prompt}

    @classmethod
    def _resolve_system_prompt(cls, context: AgentContext) -> str:
        """Resolve the system prompt from the template module for the agent's role."""
        role = context.role or ""
        _template_modules = {
            "moderator": "app.prompts.moderator",
            "pro": "app.prompts.pro",
            "con": "app.prompts.con",
            "judge": "app.prompts.judge",
        }
        module_path = _template_modules.get(role)
        if module_path:
            import importlib
            try:
                mod = importlib.import_module(module_path)
                return getattr(mod, "SYSTEM_PROMPT", "")
            except ImportError:
                pass
        return ""

    @classmethod
    def _build_user_prompt(cls, context: AgentContext) -> str:
        """Assemble the user message: preamble + history + body + suffix."""
        parts: list[str] = []

        cls._add_preamble(parts, context)
        cls._add_history(parts, context)
        cls._add_body(parts, context)
        cls._add_suffix(parts, context)

        return "\n".join(parts)

    # ── Preamble ──────────────────────────────────────────────────

    @classmethod
    def _add_preamble(cls, parts: list[str], ctx: AgentContext) -> None:
        """Topic, stance, round info — differs by role."""
        parts.append(f"Debate topic: {ctx.topic}")

        rt = ctx.response_type

        # Judge / Moderator have no stance
        if ctx.role == "judge" or rt == ResponseType.VERDICT:
            parts.append(f"Total rounds completed: {len(ctx.previous_rounds)}")
            return
        if rt in (ResponseType.MODERATOR_INTRO, ResponseType.MODERATOR_SUMMARY):
            return

        # Pro / Con stance
        if ctx.stance:
            parts.append(f"Your assigned stance: {ctx.stance}")
            parts.append(f"Your opponent argues for: {ctx.opponent_name}")
            parts.append("Argue ONLY for your assigned stance. Not for the overall question.")
        elif ctx.role == "pro":
            parts.append("Your position: FOR the proposition")
            parts.append("The opposing side argues against it.")
        elif ctx.role == "con":
            parts.append("Your position: AGAINST the proposition")
            parts.append("The proposing side argues for it.")
        elif ctx.role not in ("moderator", "judge"):
            parts.append("Your role: You argue FOR the affirmative position.")
            parts.append("The opposing side argues against it.")

        parts.append(f"Round: {ctx.round_number}")

        if ctx.round_focus:
            parts.append(f"Round focus: {ctx.round_focus}")
        if ctx.moderator_steer:
            parts.append(f"Moderator steering: {ctx.moderator_steer}")

    # ── History ───────────────────────────────────────────────────

    @classmethod
    def _add_history(cls, parts: list[str], ctx: AgentContext) -> None:
        max_chars = 4000 if ctx.response_type == ResponseType.VERDICT else 1500
        history = format_history(ctx.previous_rounds, max_chars=max_chars)
        if history:
            parts.append(f"\nDebate history:\n{history}")

    # ── Body (role- and response-type-specific instruction) ───────

    @classmethod
    def _add_body(cls, parts: list[str], ctx: AgentContext) -> None:
        rt = ctx.response_type

        # Judge role always gets the judge body regardless of response_type
        if ctx.role == "judge":
            parts.append(cls._judge_body())
        elif rt == ResponseType.VERDICT:
            parts.append(cls._judge_body())
        elif rt == ResponseType.MODERATOR_INTRO:
            parts.append(f"{_ROUTE_MARKERS[rt]}\n" + cls._moderator_intro_body())
        elif rt == ResponseType.MODERATOR_SUMMARY:
            parts.append(f"{_ROUTE_MARKERS[rt]}\n" + cls._moderator_summary_body())
        elif rt == ResponseType.REBUTTAL:
            parts.append(cls._rebuttal_body(ctx))
        elif rt == ResponseType.CROSS_EXAMINE_ASK:
            parts.append(cls._cross_examine_ask_body())
        elif rt == ResponseType.CROSS_EXAMINE_ANSWER:
            parts.append(cls._cross_examine_answer_body(ctx))
        elif rt == ResponseType.USER_ANSWER:
            parts.append(cls._user_answer_body(ctx))
        else:
            # OPENING (default) — pro / con opening argument
            parts.append(cls._opening_body())

    # ── Suffix (shared) ───────────────────────────────────────────

    @classmethod
    def _add_suffix(cls, parts: list[str], ctx: AgentContext) -> None:
        if ctx.response_type == ResponseType.VERDICT:
            parts.append(f"\nWrite your entire response in {ctx.language}. Return ONLY valid JSON.")
        else:
            parts.append(
                f"\nWrite your entire response in {ctx.language}. "
                "Use plain natural language. No Markdown, headings, bold, or bullet lists."
            )

    # ═══════════════════════════════════════════════════════════════
    #  Body template methods
    # ═══════════════════════════════════════════════════════════════

    @classmethod
    def _opening_body(cls) -> str:
        return (
            "Construct your opening argument for your assigned stance. "
            "Present 3 to 4 clear, logical points. Be concise — aim for 3-4 paragraphs."
        )

    @classmethod
    def _rebuttal_body(cls, ctx: AgentContext) -> str:
        lines = [
            "This is a REBUTTAL. Directly respond to the opponent's "
            "latest arguments. Reference specific claims and explain why "
            "they are wrong, incomplete, or overstated. Be concise.",
        ]
        if ctx.latest_opponent:
            lines.append(f"\nOpponent's latest argument:\n{ctx.latest_opponent[:500]}")
        return "\n".join(lines)

    @classmethod
    def _cross_examine_ask_body(cls) -> str:
        return (
            "Ask ONE concise question to the opposing side. "
            "Expose a weakness in their reasoning. Keep it to 2-3 sentences."
        )

    @classmethod
    def _cross_examine_answer_body(cls, ctx: AgentContext) -> str:
        lines = [
            "Answer a question from the opposing side. "
            "Defend your position. Turn it into an opportunity to strengthen your case. "
            "Be concise.",
        ]
        if ctx.cross_target:
            lines.append(f"\nQuestion to answer:\n{ctx.cross_target}")
        return "\n".join(lines)

    @classmethod
    def _user_answer_body(cls, ctx: AgentContext) -> str:
        lines = [
            "The user is asking you a direct question. "
            "Answer clearly from your assigned stance.",
        ]
        if ctx.cross_target:
            lines.append(f"\nUser's question:\n{ctx.cross_target}")
        return "\n".join(lines)

    @classmethod
    def _moderator_intro_body(cls) -> str:
        return (
            "Your task: Welcome everyone and introduce this segment of the debate. "
            "State the topic naturally. Then hand off to the first speaker."
        )

    @classmethod
    def _moderator_summary_body(cls) -> str:
        return (
            "Your task: Briefly summarise what was discussed. "
            "Identify the strongest point from each side and what remains unresolved. "
            "Keep it concise."
        )

    @classmethod
    def _judge_body(cls) -> str:
        return (
            "You are the judge. Evaluate the debate and return a JSON object "
            "with these fields:\n"
            '  "summary": A balanced natural-language summary of both sides\' arguments.\n'
            '  "recommendation": Your final recommendation to the decision-maker.\n'
            '  "winner": "pro" or "con" indicating which side presented stronger arguments.\n'
            '  "scores": An object with integer scores (0-100) for each dimension:\n'
            '    - "logic": Logical coherence and reasoning quality\n'
            '    - "evidence": Strength and relevance of evidence\n'
            '    - "rebuttal": Quality of counter-arguments and rebuttals\n'
            '    - "consistency": Consistency of position across rounds\n'
            '    - "clarity": Clarity and persuasiveness of expression\n'
            '  "confidence": A float between 0.0 and 1.0 indicating your confidence in the verdict.\n'
            '  "strengths": An array of 2-3 key strengths of the winning side.\n'
            '  "weaknesses": An array of 2-3 key weaknesses of the losing side.\n'
            "Be fair and objective. Consider the strongest points from each side."
        )


# ═══════════════════════════════════════════════════════════════════
#  Extraction helpers (used by LLMService demo mode)
# ═══════════════════════════════════════════════════════════════════


def extract_topic(prompt: str) -> str:
    """Extract the debate topic from a prompt string."""
    for line in prompt.split("\n"):
        if line.lower().startswith("debate topic:"):
            return line.split(":", 1)[1].strip()
        if line.lower().startswith("topic:"):
            return line.split(":", 1)[1].strip()
    return "this topic"


def extract_response_type(prompt: str) -> str:
    """Extract the response type from route markers or prompt content."""
    if "[ROUTE:MODERATOR_INTRO" in prompt:
        return "moderator_intro"
    if "[ROUTE:MODERATOR_SUMMARY" in prompt:
        return "moderator_summary"
    if "[ROUTE:USER_ANSWER]" in prompt:
        return "user_answer"
    if "REBUTTAL" in prompt or "rebuttal" in prompt:
        return "rebuttal"
    if "Ask ONE concise question" in prompt:
        return "cross_examine_ask"
    if "Answer a question from the opposing side" in prompt:
        return "cross_examine_answer"
    if "cross-examination" in prompt or "CROSS_EXAMINE" in prompt:
        if "asking a question" in prompt or "ask a question" in prompt:
            return "cross_examine_ask"
        if "answering a question" in prompt or "Answer" in prompt:
            return "cross_examine_answer"
        return "cross_examine_ask"
    if "user is asking" in prompt or "user question" in prompt:
        return "user_answer"
    if "round introduction" in prompt or "MODERATOR_INTRO" in prompt:
        return "moderator_intro"
    if "round summary" in prompt or "MODERATOR_SUMMARY" in prompt:
        return "moderator_summary"
    return "opening"


def extract_round_focus(prompt: str) -> str:
    """Extract the round focus from a prompt string."""
    for line in prompt.split("\n"):
        stripped = line.strip()
        if stripped.lower().startswith("round focus:"):
            return stripped.split(":", 1)[1].strip()
        if stripped.lower().startswith("this round's focus is:"):
            return stripped.split(":", 1)[1].strip()
    return "General discussion"


def extract_round(prompt: str) -> int:
    """Extract the round number from a prompt string."""
    for line in prompt.split("\n"):
        line = line.strip()
        if line.lower().startswith("round:"):
            parts = line.split(":", 1)
            try:
                return int(parts[1].strip().split()[0])
            except (ValueError, IndexError):
                pass
        if line.lower().startswith("round number:"):
            parts = line.split(":", 1)
            try:
                return int(parts[1].strip())
            except (ValueError, IndexError):
                pass
    return 1


def extract_stance(prompt: str) -> str | None:
    """Extract the assigned stance from a prompt, if set."""
    for line in prompt.split("\n"):
        stripped = line.strip()
        if stripped.lower().startswith("your assigned stance:"):
            return stripped.split(":", 1)[1].strip()
    return None


def try_parse_json(content: str) -> list[object]:
    """Attempt to parse JSON from LLM output, trying multiple formats."""
    import json
    import re
    results: list[object] = []
    try:
        results.append(json.loads(content))
    except json.JSONDecodeError:
        pass
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
    if match:
        try:
            results.append(json.loads(match.group(1)))
        except (json.JSONDecodeError, KeyError):
            pass
    match = re.search(r"\{[^{}]*\"summary\"[^{}]*\"recommendation\"[^{}]*\}", content, re.DOTALL)
    if match:
        try:
            results.append(json.loads(match.group(0)))
        except (json.JSONDecodeError, KeyError):
            pass
    return results


def extract_evidence(text: str) -> list:
    """Extract Claim/Evidence/Reasoning patterns from agent output.

    Returns a list of Evidence objects found in the text.
    """
    import re
    from app.domain.debate import Evidence
    results: list[Evidence] = []

    pattern = re.compile(
        r'(?:Claim|CLAIM|claim)[\s:]*([^\n]+?)(?:\n|\s)*'
        r'(?:Evidence|EVIDENCE|evidence)[\s:]*([^\n]+?)(?:\n|\s)*'
        r'(?:Reasoning|REASONING|reasoning)[\s:]*([^\n]+?)(?=\n\n|\n(?:Claim|CLAIM|claim)|$)',
        re.IGNORECASE | re.DOTALL,
    )
    for m in pattern.finditer(text):
        results.append(Evidence(
            claim=m.group(1).strip()[:300],
            evidence=m.group(2).strip()[:300],
            reasoning=m.group(3).strip()[:300],
        ))
    return results


def parse_judge_response(content: str) -> dict[str, object]:
    """Parse the judge's JSON response with fallback heuristic."""
    for data in try_parse_json(content):
        if isinstance(data, dict) and "summary" in data and "recommendation" in data:
            return {
                "summary": data.get("summary", ""),
                "recommendation": data.get("recommendation", ""),
                "winner": data.get("winner", ""),
                "scores": data.get("scores", {}),
                "confidence": data.get("confidence", 0.0),
                "strengths": data.get("strengths", []),
                "weaknesses": data.get("weaknesses", []),
            }
    logger.warning("Judge response could not be parsed as JSON, using heuristic fallback")
    paragraphs = [p.strip() for p in content.strip().split("\n\n") if p.strip()]
    recommendation = paragraphs[-1] if len(paragraphs) > 1 else content
    return {
        "summary": content,
        "recommendation": recommendation,
        "winner": "",
        "scores": {},
        "confidence": 0.0,
        "strengths": [],
        "weaknesses": [],
    }
