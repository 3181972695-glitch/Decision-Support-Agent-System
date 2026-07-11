"""Abstract base class for all debate agents."""

from abc import ABC, abstractmethod
from typing import Any

from app.services.llm_service import LLMService


class AgentContext:
    """Context passed to an agent for generating a response.

    Attributes:
        topic: The debate topic.
        round_number: Current round number (1-indexed).
        previous_rounds: Arguments from all prior rounds.
        moderator_steer: The moderator's steer for this round (if any).
        debate_id: Unique identifier for the debate.
    """

    def __init__(
        self,
        topic: str,
        round_number: int,
        previous_rounds: list[Any] | None = None,
        moderator_steer: str | None = None,
        debate_id: str | None = None,
    ) -> None:
        self.topic = topic
        self.round_number = round_number
        self.previous_rounds = previous_rounds or []
        self.moderator_steer = moderator_steer
        self.debate_id = debate_id


class BaseAgent(ABC):
    """Abstract agent that all debate agents inherit from.

    Subclasses must define SYSTEM_PROMPT and implement build_prompt().
    """

    SYSTEM_PROMPT: str = ""

    def __init__(self, llm_service: LLMService) -> None:
        self._llm = llm_service

    @abstractmethod
    def build_prompt(self, context: AgentContext) -> str:
        """Construct the user prompt for this agent given the debate context."""
        ...

    async def generate(self, context: AgentContext) -> str:
        """Generate a response using the LLM service.

        Template method: build_prompt() supplies the user message,
        the LLM service handles the actual API call.
        """
        prompt = self.build_prompt(context)
        return await self._llm.generate(
            prompt=prompt,
            system_prompt=self.SYSTEM_PROMPT,
        )
