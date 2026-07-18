"""Expert debate service — multi-expert analysis with cross-critique and judge.

Flow:
  Phase 1 (parallel):  Each expert independently analyses the question
  Phase 2 (parallel):  Each expert challenges every other expert's analysis
  Phase 3 (serial):    Judge synthesises all analyses + debate into a final decision
"""

from __future__ import annotations

import asyncio
import logging
import re

from app.agents.base import detect_language
from app.experts.expert_config import get_mode
from app.services.llm_service import LLMService

logger = logging.getLogger("app.services.expert_debate_service")

_NO_MD = " Use plain natural language. No Markdown, bold, headings, or bullet lists."

_LANG_INSTR = {
    "English": " Write your entire response in English.",
    "Chinese": " 用中文写你的整个回答。",
    "Japanese": " 日本語で回答してください。",
    "Korean": " 전체 응답을 한국어로 작성하세요.",
}


class ExpertDebateService:
    """Runs a structured multi-expert debate with cross-critique and a judge."""

    def __init__(self, llm_service: LLMService) -> None:
        self._llm = llm_service

    async def debate(self, mode: str, question: str) -> dict:
        """Run a full expert debate for the given mode and question.

        Returns:
            {
                "mode": display_name,
                "question": original question,
                "experts": [{"role", "analysis", "arguments"}, ...],
                "debate_rounds": [{"speaker", "response_to", "content"}, ...],
                "final_decision": str,
                "confidence": int 0-100,
                "key_tradeoffs": [str, ...],
            }
        """
        panel = get_mode(mode)
        if panel is None:
            raise ValueError(f"Unknown expert mode: {mode!r}")

        logger.info(
            "[EXPERT_DEBATE] mode=%s question=%r experts=%d",
            mode, question[:60], len(panel["experts"]),
        )

        experts = panel["experts"]
        display_name = panel["display_name"]
        lang = detect_language(question)
        lang_suffix = _LANG_INSTR.get(lang, _LANG_INSTR["English"])
        logger.info("[EXPERT_DEBATE] detected language=%s", lang)

        # ── Phase 1: parallel independent analysis ──────────────────

        async def _phase1(expert: dict) -> dict:
            role = expert["role"]
            system = expert["system_prompt"]
            prompt = (
                f"Question: {question}\n\n"
                f"Provide your analysis from the perspective of a {role}. "
                f"End with a line exactly like:\n"
                f"ARGUMENTS:arg1|arg2|arg3\n"
                f"replacing arg1, arg2, arg3 with your 2-3 strongest key points "
                f"(each a short phrase, pipe-separated).{_NO_MD}{lang_suffix}"
            )
            logger.info("[EXPERT_DEBATE] phase1 role=%s", role)
            try:
                text = await self._llm.generate(
                    system_prompt=system, prompt=prompt,
                    role=f"expert-debate-{mode}-{role}",
                )
            except Exception as exc:
                logger.warning("[EXPERT_DEBATE] phase1 error role=%s: %s", role, exc)
                text = f"Error: {exc}"

            # Parse out the ARGUMENTS: line
            arguments: list[str] = []
            cleaned = text
            m = re.search(r'^ARGUMENTS:\s*(.*)$', text, re.MULTILINE)
            if m:
                raw = m.group(1)
                arguments = [a.strip() for a in raw.split("|") if a.strip()]
                cleaned = text[:m.start()].rstrip()

            return {"role": role, "analysis": cleaned.strip(), "arguments": arguments}

        phase1_results: list[dict] = await asyncio.gather(
            *[_phase1(e) for e in experts], return_exceptions=False,
        )

        # ── Phase 2: parallel cross-critique (each expert vs each other) ──

        async def _phase2(speaker: dict, other: dict, other_analysis: str) -> dict:
            s_role = speaker["role"]
            o_role = other["role"]
            if s_role == o_role:
                return None  # skip self
            prompt = (
                f"The question is: {question}\n\n"
                f"Expert {o_role} said:\n{other_analysis[:2000]}\n\n"
                f"You are the {s_role}. Challenge {o_role}'s position. "
                f"Point out a specific weakness, blind spot, or disagreement "
                f"from your perspective. Be concise — 2-4 sentences.{_NO_MD}{lang_suffix}"
            )
            system = speaker["system_prompt"]
            logger.info("[EXPERT_DEBATE] phase2 %s → %s", s_role, o_role)
            try:
                content = await self._llm.generate(
                    system_prompt=system, prompt=prompt,
                    role=f"expert-debate-{mode}-{s_role}-vs-{o_role}",
                )
            except Exception as exc:
                logger.warning(
                    "[EXPERT_DEBATE] phase2 error %s→%s: %s", s_role, o_role, exc,
                )
                content = f"Error: {exc}"
            return {"speaker": s_role, "response_to": o_role, "content": content.strip()}

        # Build every (speaker, other) pair where speaker != other
        debate_tasks = []
        for speaker in experts:
            for other in experts:
                if speaker["role"] == other["role"]:
                    continue
                other_analysis = next(
                    r["analysis"] for r in phase1_results if r["role"] == other["role"]
                )
                debate_tasks.append(_phase2(speaker, other, other_analysis))

        phase2_results: list[dict | None] = await asyncio.gather(
            *debate_tasks, return_exceptions=False,
        )
        debate_rounds = [r for r in phase2_results if r is not None]

        # ── Phase 3: judge synthesis ───────────────────────────────

        judge_system = (
            f"You are an impartial judge synthesising a multi-expert debate.{_NO_MD}{lang_suffix}"
        )
        judge_parts = [f"Question: {question}", "", "Expert analyses:"]
        for r in phase1_results:
            judge_parts.append(f"\n--- {r['role']} ---\n{r['analysis']}")
        judge_parts.append("\n\nDebate rounds (cross-critiques):")
        for dr in debate_rounds:
            judge_parts.append(f"\n{dr['speaker']} to {dr['response_to']}: {dr['content']}")
        judge_parts.append(
            "\n\nProvide your final assessment. "
            "End with exactly one line:\n"
            "FINAL:your recommendation here\n"
            "Then a line:\n"
            "CONFIDENCE:0-100\n"
            "Then a line:\n"
            "TRADEOFFS:tradeoff1|tradeoff2|tradeoff3\n"
            "where each tradeoff is a short phrase."
            f"{_NO_MD}{lang_suffix}"
        )
        judge_prompt = "\n".join(judge_parts)

        logger.info("[EXPERT_DEBATE] phase3 judge")
        try:
            judge_text = await self._llm.generate(
                system_prompt=judge_system, prompt=judge_prompt,
                role=f"expert-debate-{mode}-judge",
            )
        except Exception as exc:
            logger.warning("[EXPERT_DEBATE] judge error: %s", exc)
            judge_text = f"Error: {exc}"

        # Parse the structured judge output
        final_decision = judge_text.strip()
        confidence = 50
        tradeoffs: list[str] = []

        m = re.search(r'^FINAL:\s*(.*)$', judge_text, re.MULTILINE)
        if m:
            final_decision = m.group(1).strip()
            # Remove the FINAL/CONFIDENCE/TRADEOFFS lines from the displayed text
            cleaned = re.sub(
                r'^FINAL:.*$|^CONFIDENCE:.*$|^TRADEOFFS:.*$',
                '', judge_text, flags=re.MULTILINE,
            ).strip()
            if cleaned:
                final_decision = cleaned

        m = re.search(r'^CONFIDENCE:\s*(\d+)', judge_text, re.MULTILINE)
        if m:
            confidence = min(100, max(0, int(m.group(1))))

        m = re.search(r'^TRADEOFFS:\s*(.*)$', judge_text, re.MULTILINE)
        if m:
            tradeoffs = [t.strip() for t in m.group(1).split("|") if t.strip()]

        return {
            "mode": f"{display_name} Debate",
            "question": question,
            "experts": phase1_results,
            "debate_rounds": debate_rounds,
            "final_decision": final_decision,
            "confidence": confidence,
            "key_tradeoffs": tradeoffs,
        }
