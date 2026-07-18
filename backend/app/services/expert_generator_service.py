"""Expert generator service — dynamically creates expert teams for any question.

Uses the LLM to determine which professional roles are needed to analyze
a given question, then generates role names, expertise descriptions, and
system prompts for each.
"""

from __future__ import annotations

import json
import logging
import re

from app.services.llm_service import LLMService

logger = logging.getLogger("app.services.expert_generator_service")

_GENERATOR_SYSTEM = (
    "You are an expert team planner. Given a user question, decide which "
    "professional roles are needed to thoroughly analyze this problem from "
    "multiple perspectives. Generate 3 to 5 experts.\n\n"
    "Return ONLY valid JSON — an array of objects with these fields:\n"
    '  "role": short professional title (e.g. "Security Engineer")\n'
    '  "expertise": one-sentence description of what this expert covers\n'
    '  "system_prompt": a detailed instruction for this expert (2-4 sentences)\n\n'
    "Rules:\n"
    "- Each role must be unique and relevant to the question.\n"
    "- Cover complementary perspectives — don't generate 3 variations of the same role.\n"
    "- System prompts should instruct the expert to analyze from their specific angle.\n"
    "- Output ONLY the JSON array, nothing else."
)


class ExpertGeneratorService:
    """Generates a tailored expert panel for any question using the LLM."""

    def __init__(self, llm_service: LLMService) -> None:
        self._llm = llm_service

    async def generate(self, question: str) -> list[dict]:
        """Generate a list of expert definitions for the given question.

        Returns:
            [{"role": str, "expertise": str, "system_prompt": str}, ...]
            3-5 experts.
        """
        if not question or not question.strip():
            raise ValueError("Question is required")

        prompt = f"Question: {question}\n\nGenerate the optimal expert team for this question."

        logger.info(
            "[EXPERT_GENERATOR] generating experts for question=%r",
            question[:60],
        )

        try:
            text = await self._llm.generate(
                system_prompt=_GENERATOR_SYSTEM,
                prompt=prompt,
                role="expert-generator",
            )
        except Exception as exc:
            logger.warning("[EXPERT_GENERATOR] LLM error: %s", exc)
            raise RuntimeError(f"Failed to generate experts: {exc}") from exc

        experts = self._parse_response(text)

        if len(experts) < 3:
            logger.warning(
                "[EXPERT_GENERATOR] only %d experts generated, padding",
                len(experts),
            )
            raise RuntimeError(
                f"Generated only {len(experts)} experts, expected at least 3"
            )

        logger.info(
            "[EXPERT_GENERATOR] generated %d experts: %s",
            len(experts), [e["role"] for e in experts],
        )
        return experts

    @staticmethod
    def _parse_response(text: str) -> list[dict]:
        """Parse the LLM response into a list of expert dicts."""
        # Try JSON parse first
        cleaned = text.strip()
        # Remove markdown code fences if present
        m = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', cleaned, re.DOTALL)
        if m:
            cleaned = m.group(1)

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            # Try to find a JSON array within the text
            m = re.search(r'\[.*?\]', cleaned, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group(0))
                except json.JSONDecodeError:
                    raise ValueError("Could not parse expert JSON from LLM response")
            else:
                raise ValueError("No JSON array found in LLM response")

        if not isinstance(data, list):
            raise ValueError("LLM response is not a JSON array")

        experts = []
        for item in data:
            if not isinstance(item, dict):
                continue
            role = item.get("role", "").strip()
            expertise = item.get("expertise", "").strip()
            system_prompt = item.get("system_prompt", "").strip()
            if role and expertise and system_prompt:
                experts.append({
                    "role": role,
                    "expertise": expertise,
                    "system_prompt": system_prompt,
                })

        return experts
