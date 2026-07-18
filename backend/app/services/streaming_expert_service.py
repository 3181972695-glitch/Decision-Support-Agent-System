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
import re
from typing import Any

from app.agents.base import detect_language
from app.experts.expert_config import get_mode
from app.services.expert_generator_service import ExpertGeneratorService
from app.services.llm_service import LLMService
from app.services.memory_service import MemoryService
from app.services.tool_service import ToolService

logger = logging.getLogger("app.services.streaming_expert_service")

_NO_MD = " Use plain natural language. No Markdown, bold, headings, or bullet lists."

_LANG_INSTR = {
    "English": " Write your entire response in English.",
    "Chinese": " 用中文写你的整个回答。",
    "Japanese": " 日本語で回答してください。",
    "Korean": " 전체 응답을 한국어로 작성하세요.",
}


def _sse(event: str, data: dict) -> str:
    """Format a Server-Sent Event string."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _phase_event(status: str) -> str:
    return _sse("phase", {"status": status})


def _build_tool_prompt(tool_service: ToolService | None) -> str:
    """Build the tool-calling instruction block for expert prompts."""
    if tool_service is None:
        return ""
    schemas = tool_service.get_tool_schemas()
    if not schemas:
        return ""

    lines = [
        "\n\nAvailable tools — you MAY use them if relevant:",
    ]
    for s in schemas:
        fn = s.get("function", s)
        name = fn.get("name", "?")
        desc = fn.get("description", "")
        params = fn.get("parameters", {}).get("properties", {})
        lines.append(f"\n- {name}: {desc}")
        if params:
            lines.append("  Parameters:")
            for pname, pinfo in params.items():
                lines.append(f"    {pname}: {pinfo.get('description', '')}")
        lines.append(
            '  To invoke, end your analysis with:\n'
            f'  TOOL_CALL:{name}|param1=value1|param2=value2'
        )
    return "\n".join(lines)


def _parse_tool_calls(text: str) -> list[dict[str, Any]]:
    """Parse TOOL_CALL: markers from expert output.

    Format: TOOL_CALL:tool_name|key=value|key=value
    Returns list of {"tool": str, "arguments": dict, "raw": str}
    """
    calls = []
    for m in re.finditer(r'^TOOL_CALL:(\w+)((?:\|[^|\n=]+=[^|\n]+)*)', text, re.MULTILINE):
        tool_name = m.group(1)
        raw_args = m.group(2)
        arguments: dict[str, str] = {}
        for pair in raw_args.split("|"):
            pair = pair.strip()
            if "=" in pair:
                key, val = pair.split("=", 1)
                arguments[key.strip()] = val.strip()
        calls.append({"tool": tool_name, "arguments": arguments, "raw": m.group(0)})
    return calls


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
        generated_experts: list[dict] = []

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
            panel = get_mode(mode)
            if panel is None:
                yield _sse("error", {"message": f"Unknown expert mode: {mode!r}"})
                return
            experts = panel["experts"]
            display_name = panel["display_name"]

        lang = detect_language(question)
        lang_suffix = _LANG_INSTR.get(lang, _LANG_INSTR["English"])

        # ── Memory retrieval ─────────────────────────────────────────
        memory_context = ""
        if self._memory is not None:
            try:
                memories = self._memory.retrieve_memory(query=question, user_id=user_id, limit=5)
                if memories:
                    memory_context = "\n\n" + self._memory.format_context(memories)
                    logger.info("[STREAM_DEBATE] retrieved %d memories", len(memories))
            except Exception as exc:
                logger.warning("[STREAM_DEBATE] memory retrieval error: %s", exc)

        # ── Tool prompt block (adds available tools info) ────────────
        tool_prompt = _build_tool_prompt(self._tool_service)

        # ── Phase 1: expert analysis (sequential with streaming) ────
        yield _phase_event("analysis")
        phase1_results: list[dict] = []

        for expert in experts:
            role = expert["role"]
            system = expert["system_prompt"] + tool_prompt
            prompt = (
                f"Question: {question}\n\n"
                f"Provide your analysis from the perspective of a {role}. "
                f"End with a line exactly like:\n"
                f"ARGUMENTS:arg1|arg2|arg3\n"
                f"replacing arg1, arg2, arg3 with your 2-3 strongest key points "
                f"(each a short phrase, pipe-separated).{_NO_MD}{lang_suffix}"
                f"{memory_context}"
            )

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
                err_msg = f"Error generating analysis: {exc}"
                collected_text = err_msg
                yield _sse("analysis_chunk", {"role": role, "content": err_msg})

            # ── Execute any tool calls found in the output ──────────
            tool_calls = _parse_tool_calls(collected_text)
            tool_evidence = ""
            for tc in tool_calls:
                yield _sse("tool_call", {
                    "expert": role,
                    "tool": tc["tool"],
                    "status": "running",
                    "arguments": tc["arguments"],
                })
                logger.info("[STREAM_DEBATE] tool_call role=%s tool=%s", role, tc["tool"])
                if self._tool_service is not None:
                    try:
                        result = await self._tool_service.execute(
                            tc["tool"], tc["arguments"],
                        )
                        tool_evidence += f"\n\nTool ({tc['tool']}) result:\n{result}"
                        yield _sse("tool_result", {
                            "expert": role,
                            "tool": tc["tool"],
                            "result": result[:500],
                        })
                    except Exception as exc:
                        logger.warning("[STREAM_DEBATE] tool_exec error: %s", exc)

            # Append tool evidence to the analysis text
            if tool_evidence:
                collected_text += tool_evidence

            # Parse ARGUMENTS line
            arguments: list[str] = []
            cleaned = collected_text
            m = re.search(r'^ARGUMENTS:\s*(.*)$', collected_text, re.MULTILINE)
            if m:
                raw = m.group(1)
                arguments = [a.strip() for a in raw.split("|") if a.strip()]
                cleaned = collected_text[:m.start()].rstrip()

            # Remove TOOL_CALL: lines from displayed output
            cleaned = re.sub(r'^TOOL_CALL:.*$', '', cleaned, flags=re.MULTILINE).strip()
            if not cleaned:
                cleaned = collected_text

            yield _sse("expert_done", {"role": role, "arguments": arguments})
            phase1_results.append({
                "role": role,
                "analysis": cleaned.strip(),
                "arguments": arguments,
            })

        # ── Phase 2: cross-critique debate rounds ───────────────────
        yield _phase_event("debate")
        debate_rounds: list[dict] = []

        for speaker in experts:
            s_role = speaker["role"]
            s_system = speaker["system_prompt"] + tool_prompt
            for other in experts:
                if s_role == other["role"]:
                    continue
                o_role = other["role"]
                other_analysis = next(
                    r["analysis"] for r in phase1_results if r["role"] == o_role
                )
                prompt = (
                    f"The question is: {question}\n\n"
                    f"Expert {o_role} said:\n{other_analysis[:2000]}\n\n"
                    f"You are the {s_role}. Challenge {o_role}'s position. "
                    f"Point out a specific weakness, blind spot, or disagreement "
                    f"from your perspective. Be concise — 2-4 sentences.{_NO_MD}{lang_suffix}"
                )

                logger.info("[STREAM_DEBATE] phase2 %s → %s", s_role, o_role)
                yield _sse("debate_start", {"speaker": s_role, "response_to": o_role})
                content = ""
                try:
                    async for chunk in self._llm.generate_stream(
                        system_prompt=s_system, prompt=prompt,
                        role=f"stream-debate-{mode}-{s_role}-vs-{o_role}",
                    ):
                        content += chunk
                        yield _sse("debate_chunk", {
                            "speaker": s_role, "response_to": o_role, "content": chunk,
                        })
                except Exception as exc:
                    logger.warning("[STREAM_DEBATE] phase2 error %s→%s: %s", s_role, o_role, exc)
                    err_msg = f"Error: {exc}"
                    content = err_msg
                    yield _sse("debate_chunk", {
                        "speaker": s_role, "response_to": o_role, "content": err_msg,
                    })

                yield _sse("debate_done", {"speaker": s_role, "response_to": o_role})
                debate_rounds.append({
                    "speaker": s_role, "response_to": o_role, "content": content.strip(),
                })

        # ── Phase 3: judge synthesis (streamed) ─────────────────────
        yield _phase_event("judge")
        judge_system = (
            f"You are an impartial judge synthesising a multi-expert debate."
            f" Experts may have used tools to gather data.{_NO_MD}{lang_suffix}"
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
            f"{_NO_MD}{lang_suffix}"
        )
        judge_prompt = "\n".join(judge_parts)

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
            err_msg = f"Error generating judge decision: {exc}"
            judge_text = err_msg
            yield _sse("judge_chunk", {"content": err_msg})

        # ── Parse structured output ─────────────────────────────────
        final_decision = judge_text.strip()
        confidence = 50
        confidence_reason: list[str] = []
        uncertainties: list[str] = []
        tradeoffs: list[str] = []

        m = re.search(r'^FINAL:\s*(.*)$', judge_text, re.MULTILINE)
        if m:
            final_decision = m.group(1).strip()
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

        # ── Store decision in memory ──────────────────────────────
        if self._memory is not None and final_decision:
            try:
                self._memory.store_decision(
                    question=question, decision=final_decision[:300],
                    confidence=confidence, mode=mode,
                )
                logger.info("[STREAM_DEBATE] stored decision memory")
            except Exception as exc:
                logger.warning("[STREAM_DEBATE] memory storage error: %s", exc)

        # ── Emit final result ───────────────────────────────────────
        yield _sse("judge_done", {
            "final_decision": final_decision,
            "confidence": confidence,
            "confidence_reason": confidence_reason,
            "uncertainties": uncertainties,
            "key_tradeoffs": tradeoffs,
        })

        yield _sse("result", {
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
        })

        yield _phase_event("complete")
        logger.info("[STREAM_DEBATE] complete")
