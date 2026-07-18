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
from app.services.expert_generator_service import ExpertGeneratorService
from app.services.llm_service import LLMService
from app.services.memory_service import MemoryService
from app.services.tool_service import ToolService
from app.services.streaming_expert_service import _build_tool_prompt, _parse_tool_calls

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

    def __init__(
        self,
        llm_service: LLMService,
        expert_generator: ExpertGeneratorService | None = None,
        memory_service: MemoryService | None = None,
        tool_service: ToolService | None = None,
    ) -> None:
        self._llm = llm_service
        self._expert_generator = expert_generator
        self._memory = memory_service
        self._tool_service = tool_service

    async def debate(
        self, mode: str, question: str,
        user_id: str = "demo_user",
    ) -> dict:
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
        generated_experts: list[dict] = []

        if mode == "dynamic":
            if self._expert_generator is None:
                raise ValueError(
                    "Dynamic mode is not available — ExpertGeneratorService not configured"
                )
            logger.info("[EXPERT_DEBATE] dynamic mode, generating experts for question=%r", question[:60])
            raw_experts = await self._expert_generator.generate(question)
            experts = raw_experts
            display_name = f"Dynamic Expert Debate"
            generated_experts = [
                {"role": e["role"], "expertise": e.get("expertise", "")}
                for e in raw_experts
            ]
            logger.info(
                "[EXPERT_DEBATE] dynamic mode generated %d experts: %s",
                len(experts), [e["role"] for e in experts],
            )
        else:
            panel = get_mode(mode)
            if panel is None:
                raise ValueError(f"Unknown expert mode: {mode!r}")
            experts = panel["experts"]
            display_name = panel["display_name"]
            logger.info(
                "[EXPERT_DEBATE] mode=%s question=%r experts=%d",
                mode, question[:60], len(experts),
            )
        lang = detect_language(question)
        lang_suffix = _LANG_INSTR.get(lang, _LANG_INSTR["English"])
        logger.info("[EXPERT_DEBATE] detected language=%s", lang)

        # ── Memory retrieval ─────────────────────────────────────────
        memory_context = ""
        if self._memory is not None:
            try:
                memories = self._memory.retrieve_memory(query=question, user_id=user_id, limit=5)
                if memories:
                    memory_context = "\n\n" + self._memory.format_context(memories)
                    logger.info(
                        "[EXPERT_DEBATE] retrieved %d memories for user=%s",
                        len(memories), user_id,
                    )
            except Exception as exc:
                logger.warning("[EXPERT_DEBATE] memory retrieval error: %s", exc)

        # ── Phase 1: parallel independent analysis ──────────────────

        async def _phase1(expert: dict) -> dict:
            role = expert["role"]
            system = expert["system_prompt"] + _build_tool_prompt(self._tool_service)
            prompt = (
                f"Question: {question}\n\n"
                f"Provide your analysis from the perspective of a {role}. "
                f"End with a line exactly like:\n"
                f"ARGUMENTS:arg1|arg2|arg3\n"
                f"replacing arg1, arg2, arg3 with your 2-3 strongest key points "
                f"(each a short phrase, pipe-separated).{_NO_MD}{lang_suffix}"
                f"{memory_context}"
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

            # ── Execute any tool calls found in the output ──────────
            tool_calls = _parse_tool_calls(text)
            for tc in tool_calls:
                if self._tool_service is not None:
                    try:
                        result = await self._tool_service.execute(
                            tc["tool"], tc["arguments"],
                        )
                        text += f"\n\nTool ({tc['tool']}) result:\n{result}"
                    except Exception as exc:
                        logger.warning("[EXPERT_DEBATE] tool error: %s", exc)

            # Parse out the ARGUMENTS: line
            arguments: list[str] = []
            cleaned = text
            m = re.search(r'^ARGUMENTS:\s*(.*)$', text, re.MULTILINE)
            if m:
                raw = m.group(1)
                arguments = [a.strip() for a in raw.split("|") if a.strip()]
                cleaned = text[:m.start()].rstrip()

            import re as _re
            cleaned = _re.sub(r'^TOOL_CALL:.*$', '', cleaned, flags=_re.MULTILINE).strip()
            if not cleaned:
                cleaned = text.strip()
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
            system = speaker["system_prompt"] + _build_tool_prompt(self._tool_service)
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
            "End with exactly these lines:\n"
            "FINAL:your recommendation here\n"
            "CONFIDENCE:0-100\n"
            "CONFIDENCE_REASON:reason1|reason2\n"
            "UNCERTAINTIES:uncertainty1|uncertainty2\n"
            "TRADEOFFS:tradeoff1|tradeoff2|tradeoff3\n"
            "where CONFIDENCE_REASON lists 1-3 reasons for your confidence level,\n"
            "UNCERTAINTIES lists 1-3 remaining unknowns or assumptions,\n"
            "and each tradeoff is a short phrase."
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
        confidence_reason: list[str] = []
        uncertainties: list[str] = []
        tradeoffs: list[str] = []

        m = re.search(r'^FINAL:\s*(.*)$', judge_text, re.MULTILINE)
        if m:
            final_decision = m.group(1).strip()
            # Remove the marker lines from the displayed text
            cleaned = re.sub(
                r'^FINAL:.*$|^CONFIDENCE:.*$|^CONFIDENCE_REASON:.*$|^UNCERTAINTIES:.*$|^TRADEOFFS:.*$',
                '', judge_text, flags=re.MULTILINE,
            ).strip()
            if cleaned:
                final_decision = cleaned

        m = re.search(r'^CONFIDENCE:\s*(\d+)', judge_text, re.MULTILINE)
        if m:
            confidence = min(100, max(0, int(m.group(1))))

        m = re.search(r'^CONFIDENCE_REASON:\s*(.*)$', judge_text, re.MULTILINE)
        if m:
            confidence_reason = [r.strip() for r in m.group(1).split("|") if r.strip()]

        m = re.search(r'^UNCERTAINTIES:\s*(.*)$', judge_text, re.MULTILINE)
        if m:
            uncertainties = [u.strip() for u in m.group(1).split("|") if u.strip()]

        m = re.search(r'^TRADEOFFS:\s*(.*)$', judge_text, re.MULTILINE)
        if m:
            tradeoffs = [t.strip() for t in m.group(1).split("|") if t.strip()]

        # Store decision in memory
        if self._memory is not None and final_decision:
            try:
                decision_text = final_decision[:300]
                self._memory.store_decision(
                    question=question, decision=decision_text,
                    confidence=confidence, mode=mode,
                )
                logger.info("[EXPERT_DEBATE] stored decision memory")
            except Exception as exc:
                logger.warning("[EXPERT_DEBATE] memory storage error: %s", exc)

        return {
            "mode": f"{display_name} Debate" if mode != "dynamic" else display_name,
            "question": question,
            "generated_experts": generated_experts,
            "experts": phase1_results,
            "debate_rounds": debate_rounds,
            "final_decision": final_decision,
            "confidence": confidence,
            "confidence_reason": confidence_reason,
            "uncertainties": uncertainties,
            "key_tradeoffs": tradeoffs,
        }
