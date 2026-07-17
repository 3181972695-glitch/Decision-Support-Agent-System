"""Expert analysis service — orchestrates multi-expert LLM calls.

For a given mode and question:
  1. Loads the expert panel from expert_config
  2. Calls LLMService.generate() for each expert in parallel
  3. Calls LLMService.generate() as a decision-maker to synthesize
  4. Returns structured results
"""

from __future__ import annotations

import asyncio
import logging

from app.experts.expert_config import get_mode
from app.services.llm_service import LLMService

logger = logging.getLogger("app.services.expert_service")


class ExpertService:
    """Stateless service that runs expert analysis panels."""

    def __init__(self, llm_service: LLMService) -> None:
        self._llm = llm_service

    async def analyze(self, mode: str, question: str) -> dict:
        """Run a full expert analysis for the given mode and question.

        Returns:
            {
                "mode": display_name,
                "question": original question,
                "experts": [{"role": str, "analysis": str}, ...],
                "final_decision": str,
            }
        """
        panel = get_mode(mode)
        if panel is None:
            raise ValueError(f"Unknown expert mode: {mode!r}")

        logger.info(
            "[EXPERT] mode=%s question=%r experts=%d",
            mode, question[:60], len(panel["experts"]),
        )

        # Step 1: Run all experts in parallel
        async def _run_expert(expert: dict) -> dict:
            role = expert["role"]
            system = expert["system_prompt"]
            logger.info("[EXPERT] calling role=%s", role)
            try:
                analysis = await self._llm.generate(
                    system_prompt=system,
                    prompt=f"Question: {question}\n\nRespond in plain natural language. No Markdown, headings, bold, or bullet lists.",
                    role=f"expert-{mode}-{role}",
                )
                logger.info("[EXPERT] done role=%s len=%d", role, len(analysis))
            except Exception as exc:
                logger.warning("[EXPERT] error role=%s: %s", role, exc)
                analysis = f"Error generating analysis: {exc}"
            return {"role": role, "analysis": analysis}

        expert_results = await asyncio.gather(
            *[_run_expert(e) for e in panel["experts"]],
            return_exceptions=False,
        )

        # Step 2: Synthesize final decision
        system_prompt = panel["decision_prompt"]
        decision_prompt_lines = [
            f"Question: {question}",
            "",
            "Expert analyses:",
        ]
        for er in expert_results:
            decision_prompt_lines.append(f"\n--- {er['role']} ---")
            decision_prompt_lines.append(er["analysis"])
        decision_prompt_lines.append(
            "\nProvide your final recommendation based on all expert opinions above. "
            "Respond in plain natural language. No Markdown, headings, bold, or bullet lists."
        )
        decision_prompt = "\n".join(decision_prompt_lines)

        logger.info("[EXPERT] calling decision-maker")
        try:
            final_decision = await self._llm.generate(
                system_prompt=system_prompt,
                prompt=decision_prompt,
                role=f"expert-{mode}-decision",
            )
        except Exception as exc:
            logger.warning("[EXPERT] decision-maker error: %s", exc)
            final_decision = f"Error generating final decision: {exc}"

        return {
            "mode": panel["display_name"],
            "question": question,
            "experts": expert_results,
            "final_decision": final_decision,
        }
