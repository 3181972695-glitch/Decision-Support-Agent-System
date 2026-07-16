"""Pro Agent — argues for the assigned stance within the debate."""

from app.agents.base import BaseAgent
from app.agents.registry import AgentRegistry
from app.prompts.pro import SYSTEM_PROMPT


@AgentRegistry.register("pro")
class ProAgent(BaseAgent):
    """Persuasive agent arguing FOR the assigned stance.

    Prompt construction is handled entirely by PromptBuilder.
    SYSTEM_PROMPT is defined in app/prompts/pro.py.
    """

    SYSTEM_PROMPT = SYSTEM_PROMPT
