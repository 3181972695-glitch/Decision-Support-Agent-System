"""Con Agent — argues against the assigned stance within the debate."""

from app.agents.base import BaseAgent
from app.agents.registry import AgentRegistry
from app.prompts.con import SYSTEM_PROMPT


@AgentRegistry.register("con")
class ConAgent(BaseAgent):
    """Persuasive agent arguing against the Pro's assigned stance / for the opposing side.

    Prompt construction is handled entirely by PromptBuilder.
    SYSTEM_PROMPT is defined in app/prompts/con.py.
    """

    SYSTEM_PROMPT = SYSTEM_PROMPT
