"""Expert debate service — multi-expert analysis with cross-critique and judge.

Flow:
  Phase 1 (parallel):  Each expert independently analyses the question
  Phase 2 (parallel):  Each expert challenges every other expert's analysis
  Phase 3 (serial):    Judge synthesises all analyses + debate into a final decision
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.services.base_debate import (
    build_memory_context,
    build_phase1_prompt,
    build_phase2_prompt,
    build_judge_prompts,
    build_tool_prompt,
    execute_tool_calls,
    get_lang_suffix,
    parse_arguments,
    parse_structured_output,
    resolve_experts,
    store_decision,
)
from app.services.expert_generator_service import ExpertGeneratorService
from app.services.llm_service import LLMService
from app.services.memory_service import MemoryService
from app.services.tool_service import ToolService

logger = logging.getLogger("app.services.expert_debate_service")


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
        """Run a full expert debate for the given mode and question."""
        experts, display_name, generated_experts = await resolve_experts(
            mode, question, self._expert_generator,
        )

        lang_suffix = get_lang_suffix(question)
        memory_context = await build_memory_context(self._memory, question, user_id)
        tool_prompt = build_tool_prompt(self._tool_service)
        display_mode = f"{display_name} Debate" if mode != "dynamic" else display_name

        # ── Phase 1: parallel independent analysis ──────────────────

        async def _phase1(expert: dict) -> dict:
            role = expert["role"]
            system = expert["system_prompt"] + tool_prompt
            prompt = build_phase1_prompt(question, role, lang_suffix, memory_context)
            logger.info("[EXPERT_DEBATE] phase1 role=%s", role)
            try:
                text = await self._llm.generate(
                    system_prompt=system, prompt=prompt,
                    role=f"expert-debate-{mode}-{role}",
                )
            except Exception as exc:
                logger.warning("[EXPERT_DEBATE] phase1 error role=%s: %s", role, exc)
                text = f"Error: {exc}"

            text, _ = await execute_tool_calls(text, role, self._tool_service)
            analysis, arguments = parse_arguments(text)
            return {"role": role, "analysis": analysis, "arguments": arguments}

        phase1_results: list[dict] = await asyncio.gather(
            *[_phase1(e) for e in experts], return_exceptions=False,
        )

        # ── Phase 2: parallel cross-critique ────────────────────────

        async def _phase2(speaker: dict, other: dict, other_analysis: str) -> dict | None:
            s_role, o_role = speaker["role"], other["role"]
            if s_role == o_role:
                return None
            prompt = build_phase2_prompt(question, s_role, o_role, other_analysis, lang_suffix)
            system = speaker["system_prompt"] + tool_prompt
            logger.info("[EXPERT_DEBATE] phase2 %s → %s", s_role, o_role)
            try:
                content = await self._llm.generate(
                    system_prompt=system, prompt=prompt,
                    role=f"expert-debate-{mode}-{s_role}-vs-{o_role}",
                )
            except Exception as exc:
                logger.warning("[EXPERT_DEBATE] phase2 error %s→%s: %s", s_role, o_role, exc)
                content = f"Error: {exc}"
            return {"speaker": s_role, "response_to": o_role, "content": content.strip()}

        debate_tasks = []
        for speaker in experts:
            for other in experts:
                if speaker["role"] == other["role"]:
                    continue
                other_analysis = next(
                    r["analysis"] for r in phase1_results if r["role"] == other["role"]
                )
                debate_tasks.append(_phase2(speaker, other, other_analysis))

        phase2_results = await asyncio.gather(*debate_tasks, return_exceptions=False)
        debate_rounds = [r for r in phase2_results if r is not None]

        # ── Phase 3: judge synthesis ───────────────────────────────

        judge_system, judge_prompt = build_judge_prompts(
            question, phase1_results, debate_rounds, lang_suffix,
        )
        logger.info("[EXPERT_DEBATE] phase3 judge")
        try:
            judge_text = await self._llm.generate(
                system_prompt=judge_system, prompt=judge_prompt,
                role=f"expert-debate-{mode}-judge",
                max_tokens=16384,
            )
        except Exception as exc:
            logger.warning("[EXPERT_DEBATE] judge error: %s", exc)
            judge_text = f"Error: {exc}"

        parsed = parse_structured_output(judge_text)
        store_decision(self._memory, question, parsed["final_decision"], parsed["confidence"], mode)

        return {
            "mode": display_mode,
            "question": question,
            "generated_experts": generated_experts,
            "experts": phase1_results,
            "debate_rounds": debate_rounds,
            **parsed,
        }
