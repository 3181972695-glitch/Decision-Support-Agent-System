"""Judge Agent — produces the final verdict with structured evaluation."""

from app.agents.base import BaseAgent
from app.agents.registry import AgentRegistry
from app.prompts.judge import SYSTEM_PROMPT


@AgentRegistry.register("judge")
class Judge(BaseAgent):
    """Impartial judge that evaluates all rounds and produces a verdict.

    Prompt construction is handled entirely by PromptBuilder.
    SYSTEM_PROMPT is defined in app/prompts/judge.py.
    """

    SYSTEM_PROMPT = SYSTEM_PROMPT
