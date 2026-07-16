"""Moderator Agent — debate moderator that guides discussion naturally."""

from app.agents.base import BaseAgent
from app.agents.registry import AgentRegistry
from app.prompts.moderator import ROUND_FOCUSES, SYSTEM_PROMPT, get_round_focus  # noqa: F401

# Exported for use by debate_service
__all__ = ["Moderator", "get_round_focus", "ROUND_FOCUSES"]


@AgentRegistry.register("moderator")
class Moderator(BaseAgent):
    """Debate moderator that guides the discussion naturally.

    Prompt construction is handled entirely by PromptBuilder.
    SYSTEM_PROMPT is defined in app/prompts/moderator.py.
    """

    SYSTEM_PROMPT = SYSTEM_PROMPT
