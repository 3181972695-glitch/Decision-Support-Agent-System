"""Streaming expert debate service — yields SSE events for real-time UI updates.

Each phase of the expert debate streams events as they happen:
  Phase 0: expert generation (dynamic mode only)
  Phase 1: expert analysis (streamed token by token, with optional tool calls)
  Phase 2: cross-critique debate rounds
  Phase 3: judge synthesis
  Final:   complete result with metadata
"""

from __future__ import annotations

import json
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

logger = logging.getLogger("app.services.streaming_expert_service")


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _phase_event(status: str) -> str:
    return _sse("phase", {"status": status})


class StreamingExpertDebateService:
    """Streaming version of the expert debate pipeline."""

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

    async def stream_debate(
        self, mode: str, question: str,
        user_id: str = "demo_user",
    ) -> "Any":  # async generator yielding str
        """Run the expert debate and yield SSE events."""
        # ── Resolve experts ─────────────────────────────────────────
        if mode == "dynamic":
            if self._expert_generator is None:
                yield _sse("error", {"message": "Dynamic mode not available"})
                return
            yield _phase_event("expert_generation")
            yield _sse("expert_generation", {"status": "started", "question": question})
            try:
                raw_experts = await self._expert_generator.generate(question)
            except Exception as exc:
                yield _sse("error", {"message": str(exc)})
                return
            experts = raw_experts
            display_name = "Dynamic Expert Debate"
            generated_experts = [
                {"role": e["role"], "expertise": e.get("expertise", "")}
                for e in raw_experts
            ]
            for ge in generated_experts:
                yield _sse("expert_generated", ge)
            yield _sse("expert_generation", {"status": "complete"})
        else:
            try:
                experts, display_name, generated_experts = await resolve_experts(
                    mode, question, self._expert_generator,
                )
            except ValueError as exc:
                yield _sse("error", {"message": str(exc)})
                return

        lang_suffix = get_lang_suffix(question)
        memory_context = await build_memory_context(self._memory, question, user_id)
        tool_prompt = build_tool_prompt(self._tool_service)
        display_mode = f"{display_name} Debate" if mode != "dynamic" else display_name

        # ── Phase 1: expert analysis (sequential with streaming) ────
        yield _phase_event("analysis")
        phase1_results: list[dict] = []

        for expert in experts:
            role = expert["role"]
            system = expert["system_prompt"] + tool_prompt
            prompt = build_phase1_prompt(question, role, lang_suffix, memory_context)

            yield _sse("expert_start", {"role": role})
            logger.info("[STREAM_DEBATE] phase1 role=%s starting", role)
            collected_text = ""
            try:
                async for chunk in self._llm.generate_stream(
                    system_prompt=system, prompt=prompt,
                    role=f"stream-debate-{mode}-{role}",
                ):
                    collected_text += chunk
                    yield _sse("analysis_chunk", {"role": role, "content": chunk})
            except Exception as exc:
                logger.warning("[STREAM_DEBATE] phase1 error role=%s: %s", role, exc)
                collected_text = f"Error generating analysis: {exc}"
                yield _sse("analysis_chunk", {"role": role, "content": collected_text})

            # Execute tool calls, emit SSE events
            collected_text, tool_log = await execute_tool_calls(collected_text, role, self._tool_service)
            for tc in tool_log:
                yield _sse("tool_call", {
                    "expert": role, "tool": tc["tool"],
                    "status": "running", "arguments": tc.get("arguments"),
                })
                if tc["status"] == "complete":
                    yield _sse("tool_result", {
                        "expert": role, "tool": tc["tool"],
                        "result": tc.get("result", ""),
                    })

            analysis, arguments = parse_arguments(collected_text)
            yield _sse("expert_done", {"role": role, "arguments": arguments})
            phase1_results.append({"role": role, "analysis": analysis, "arguments": arguments})

        # ── Phase 2: cross-critique debate rounds ───────────────────
        yield _phase_event("debate")
        debate_rounds: list[dict] = []

        for speaker in experts:
            s_role, s_sys = speaker["role"], speaker["system_prompt"] + tool_prompt
            for other in experts:
                if s_role == other["role"]:
                    continue
                o_role = other["role"]
                other_analysis = next(
                    r["analysis"] for r in phase1_results if r["role"] == o_role
                )
                prompt = build_phase2_prompt(question, s_role, o_role, other_analysis, lang_suffix)

                logger.info("[STREAM_DEBATE] phase2 %s → %s", s_role, o_role)
                yield _sse("debate_start", {"speaker": s_role, "response_to": o_role})
                content = ""
                try:
                    async for chunk in self._llm.generate_stream(
                        system_prompt=s_sys, prompt=prompt,
                        role=f"stream-debate-{mode}-{s_role}-vs-{o_role}",
                    ):
                        content += chunk
                        yield _sse("debate_chunk", {
                            "speaker": s_role, "response_to": o_role, "content": chunk,
                        })
                except Exception as exc:
                    logger.warning("[STREAM_DEBATE] phase2 error %s→%s: %s", s_role, o_role, exc)
                    content = f"Error: {exc}"
                    yield _sse("debate_chunk", {
                        "speaker": s_role, "response_to": o_role, "content": content,
                    })

                yield _sse("debate_done", {"speaker": s_role, "response_to": o_role})
                debate_rounds.append({"speaker": s_role, "response_to": o_role, "content": content.strip()})

        # ── Phase 3: judge synthesis ───────────────────────────────
        yield _phase_event("judge")
        judge_system, judge_prompt = build_judge_prompts(
            question, phase1_results, debate_rounds, lang_suffix,
        )

        logger.info("[STREAM_DEBATE] phase3 judge")
        yield _sse("judge_start", {})
        judge_text = ""
        try:
            async for chunk in self._llm.generate_stream(
                system_prompt=judge_system, prompt=judge_prompt,
                role=f"stream-debate-{mode}-judge",
            ):
                judge_text += chunk
                yield _sse("judge_chunk", {"content": chunk})
        except Exception as exc:
            logger.warning("[STREAM_DEBATE] judge error: %s", exc)
            judge_text = f"Error generating judge decision: {exc}"
            yield _sse("judge_chunk", {"content": judge_text})

        parsed = parse_structured_output(judge_text)
        store_decision(self._memory, question, parsed["final_decision"], parsed["confidence"], mode)

        yield _sse("judge_done", {
            "final_decision": parsed["final_decision"],
            "confidence": parsed["confidence"],
            "confidence_reason": parsed["confidence_reason"],
            "uncertainties": parsed["uncertainties"],
            "key_tradeoffs": parsed["key_tradeoffs"],
        })
        yield _sse("result", {
            "mode": display_mode,
            "question": question,
            "generated_experts": generated_experts,
            "experts": phase1_results,
            "debate_rounds": debate_rounds,
            **parsed,
        })
        yield _phase_event("complete")
        logger.info("[STREAM_DEBATE] complete")
