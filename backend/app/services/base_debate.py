"""Shared utilities for expert debate services.

Extracts common logic used by both ExpertDebateService (parallel)
and StreamingExpertDebateService (sequential/streaming) to eliminate
~200 lines of duplication.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.agents.base import detect_language
from app.experts.expert_config import get_mode
from app.services.expert_generator_service import ExpertGeneratorService
from app.services.memory_service import MemoryService
from app.services.tool_service import ToolService

logger = logging.getLogger("app.services.base_debate")

_NO_MD = " Use plain natural language. No Markdown, bold, headings, or bullet lists."

_LANG_INSTR = {
    "English": " Write your entire response in English.",
    "Chinese": " 用中文写你的整个回答。",
    "Japanese": " 日本語で回答してください。",
    "Korean": " 전체 응답을 한국어로 작성하세요.",
}

# ── Expert resolution ─────────────────────────────────────────────


async def resolve_experts(
    mode: str,
    question: str,
    expert_generator: ExpertGeneratorService | None = None,
) -> tuple[list[dict[str, Any]], str, list[dict[str, Any]]]:
    """Resolve the expert panel from a mode or dynamic generation.

    Returns (experts, display_name, generated_experts_metadata).
    generated_experts_metadata is empty for static modes.
    """
    generated_experts: list[dict[str, Any]] = []

    if mode == "dynamic":
        if expert_generator is None:
            raise ValueError("Dynamic mode is not available — ExpertGeneratorService not configured")
        logger.info("[DEBATE] dynamic mode, generating experts for question=%r", question[:60])
        raw_experts = await expert_generator.generate(question)
        display_name = "Dynamic Expert Debate"
        generated_experts = [
            {"role": e["role"], "expertise": e.get("expertise", "")}
            for e in raw_experts
        ]
        logger.info("[DEBATE] generated %d experts: %s", len(raw_experts), [e["role"] for e in raw_experts])
        return raw_experts, display_name, generated_experts

    panel = get_mode(mode)
    if panel is None:
        raise ValueError(f"Unknown expert mode: {mode!r}")
    logger.info("[DEBATE] mode=%s question=%r experts=%d", mode, question[:60], len(panel["experts"]))
    return panel["experts"], panel["display_name"], generated_experts


def get_lang_suffix(question: str) -> str:
    """Detect language and return the appropriate suffix."""
    lang = detect_language(question)
    return _LANG_INSTR.get(lang, _LANG_INSTR["English"])


# ── Memory ─────────────────────────────────────────────────────────


async def build_memory_context(
    memory_service: MemoryService | None,
    question: str,
    user_id: str = "demo_user",
) -> str:
    """Retrieve relevant memories and format as context string."""
    if memory_service is None:
        return ""
    try:
        memories = await _retrieve_memories(memory_service, question, user_id)
        if memories:
            return "\n\n" + memory_service.format_context(memories)
    except Exception as exc:
        logger.warning("[DEBATE] memory retrieval error: %s", exc)
    return ""


async def _retrieve_memories(
    memory_service: MemoryService,
    question: str,
    user_id: str,
) -> list[dict[str, Any]]:
    """Wrapper to call memory_service.retrieve_memory (synchronous SQLite call)."""
    return memory_service.retrieve_memory(query=question, user_id=user_id, limit=5)


def store_decision(
    memory_service: MemoryService | None,
    question: str,
    final_decision: str,
    confidence: int,
    mode: str,
) -> None:
    """Store a debate decision in memory."""
    if memory_service is None or not final_decision:
        return
    try:
        memory_service.store_decision(
            question=question,
            decision=final_decision[:300],
            confidence=confidence,
            mode=mode,
        )
        logger.info("[DEBATE] stored decision memory")
    except Exception as exc:
        logger.warning("[DEBATE] memory storage error: %s", exc)


# ── Tools ──────────────────────────────────────────────────────────


def build_tool_prompt(tool_service: ToolService | None) -> str:
    """Build the tool-calling instruction block for expert prompts."""
    if tool_service is None:
        return ""
    schemas = tool_service.get_tool_schemas()
    if not schemas:
        return ""

    lines = ["\n\nAvailable tools — you MAY use them if relevant:"]
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


def parse_tool_calls(text: str) -> list[dict[str, Any]]:
    """Parse TOOL_CALL: markers from expert output."""
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


async def execute_tool_calls(
    text: str,
    role: str,
    tool_service: ToolService | None,
) -> tuple[str, list[dict[str, Any]]]:
    """Execute tools found in text and return (updated_text, tool_call_log).

    Tool call log entries have {tool, arguments, status, result}.
    """
    tool_calls = parse_tool_calls(text)
    tool_call_log: list[dict[str, Any]] = []
    tool_evidence = ""

    for tc in tool_calls:
        log_entry = {
            "expert": role,
            "tool": tc["tool"],
            "arguments": tc["arguments"],
            "status": "running",
        }
        tool_call_log.append(log_entry)

        if tool_service is not None:
            try:
                result = await tool_service.execute(tc["tool"], tc["arguments"])
                tool_evidence += f"\n\nTool ({tc['tool']}) result:\n{result}"
                log_entry["status"] = "complete"
                log_entry["result"] = result[:500]
            except Exception as exc:
                logger.warning("[DEBATE] tool execution error: %s", exc)
                log_entry["status"] = "error"
                log_entry["result"] = str(exc)[:200]

    if tool_evidence:
        text += tool_evidence

    return text, tool_call_log


def clean_tool_call_lines(text: str) -> str:
    """Remove TOOL_CALL: lines from display text."""
    return re.sub(r'^TOOL_CALL:.*$', '', text, flags=re.MULTILINE).strip()


# ── Prompt construction ────────────────────────────────────────────


def build_phase1_prompt(
    question: str,
    role: str,
    lang_suffix: str,
    memory_context: str = "",
    tool_prompt: str = "",
) -> str:
    """Build the Phase 1 expert analysis prompt."""
    parts = [
        f"Question: {question}",
        "",
        f"Provide your analysis from the perspective of a {role}. ",
        "End with a line exactly like:",
        "ARGUMENTS:arg1|arg2|arg3",
        "replacing arg1, arg2, arg3 with your 2-3 strongest key points "
        "(each a short phrase, pipe-separated).",
        _NO_MD,
        lang_suffix,
    ]
    if memory_context:
        parts.append(memory_context)
    return "\n".join(parts)


def build_phase2_prompt(
    question: str,
    s_role: str,
    o_role: str,
    other_analysis: str,
    lang_suffix: str,
) -> str:
    """Build the Phase 2 cross-critique prompt."""
    return (
        f"The question is: {question}\n\n"
        f"Expert {o_role} said:\n{other_analysis[:2000]}\n\n"
        f"You are the {s_role}. Challenge {o_role}'s position. "
        f"Point out a specific weakness, blind spot, or disagreement "
        f"from your perspective. Be concise — 2-4 sentences."
        f"{_NO_MD}{lang_suffix}"
    )


def build_judge_prompts(
    question: str,
    phase1_results: list[dict[str, Any]],
    debate_rounds: list[dict[str, Any]],
    lang_suffix: str,
) -> tuple[str, str]:
    """Build judge system prompt and user prompt.

    Returns (system_prompt, user_prompt).
    """
    system = f"You are an impartial judge synthesising a multi-expert debate. Experts may have used tools to gather data.{_NO_MD}{lang_suffix}"

    parts = [f"Question: {question}", "", "Expert analyses:"]
    for r in phase1_results:
        parts.append(f"\n--- {r['role']} ---\n{r['analysis']}")
    parts.append("\n\nDebate rounds (cross-critiques):")
    for dr in debate_rounds:
        parts.append(f"\n{dr['speaker']} to {dr['response_to']}: {dr['content']}")
    parts.append(
        "\n\nProvide your final assessment. "
        "End with exactly these lines:\n"
        "FINAL:your recommendation here\n"
        "CONFIDENCE:0-100\n"
        "CONFIDENCE_REASON:reason1|reason2\n"
        "UNCERTAINTIES:uncertainty1|uncertainty2\n"
        "TRADEOFFS:tradeoff1|tradeoff2|tradeoff3\n"
        f"{_NO_MD}{lang_suffix}"
    )
    return system, "\n".join(parts)


def parse_arguments(text: str) -> tuple[str, list[str]]:
    """Parse ARGUMENTS: line from text.

    Returns (cleaned_text, arguments_list).
    """
    arguments: list[str] = []
    cleaned = text
    m = re.search(r'^ARGUMENTS:\s*(.*)$', text, re.MULTILINE)
    if m:
        raw = m.group(1)
        arguments = [a.strip() for a in raw.split("|") if a.strip()]
        cleaned = text[:m.start()].rstrip()
    cleaned = clean_tool_call_lines(cleaned)
    if not cleaned:
        cleaned = text.strip()
    return cleaned.strip(), arguments


def parse_structured_output(judge_text: str) -> dict[str, Any]:
    """Parse structured judge output (FINAL/CONFIDENCE/etc.).

    Returns dict with keys: final_decision, confidence, confidence_reason,
    uncertainties, key_tradeoffs.
    """
    result: dict[str, Any] = {
        "final_decision": judge_text.strip(),
        "confidence": 50,
        "confidence_reason": [],
        "uncertainties": [],
        "key_tradeoffs": [],
    }

    m = re.search(r'^FINAL:\s*(.*)$', judge_text, re.MULTILINE)
    if m:
        result["final_decision"] = m.group(1).strip()
        cleaned = re.sub(
            r'^FINAL:.*$|^CONFIDENCE:.*$|^CONFIDENCE_REASON:.*$|^UNCERTAINTIES:.*$|^TRADEOFFS:.*$',
            '', judge_text, flags=re.MULTILINE,
        ).strip()
        if cleaned:
            result["final_decision"] = cleaned

    m = re.search(r'^CONFIDENCE:\s*(\d+)', judge_text, re.MULTILINE)
    if m:
        result["confidence"] = min(100, max(0, int(m.group(1))))

    m = re.search(r'^CONFIDENCE_REASON:\s*(.*)$', judge_text, re.MULTILINE)
    if m:
        result["confidence_reason"] = [r.strip() for r in m.group(1).split("|") if r.strip()]

    m = re.search(r'^UNCERTAINTIES:\s*(.*)$', judge_text, re.MULTILINE)
    if m:
        result["uncertainties"] = [u.strip() for u in m.group(1).split("|") if u.strip()]

    m = re.search(r'^TRADEOFFS:\s*(.*)$', judge_text, re.MULTILINE)
    if m:
        result["key_tradeoffs"] = [t.strip() for t in m.group(1).split("|") if t.strip()]

    return result
