"""Moderator Agent — manages the debate flow and steers discussion."""

from app.agents.base import AgentContext, BaseAgent
from app.agents.registry import AgentRegistry


@AgentRegistry.register("moderator")
class Moderator(BaseAgent):
    """Neutral moderator that steers the debate each round."""

    SYSTEM_PROMPT = (
        "You are a neutral and insightful debate moderator. "
        "Your role is to summarise how the debate is progressing "
        "and provide a steer to guide both sides toward deeper "
        "analysis in the next round. "
        "Do not take sides — remain impartial."
    )

    def build_prompt(self, context: AgentContext) -> str:
        prompt_lines = [f"Debate topic: {context.topic}"]
        prompt_lines.append(f"Round: {context.round_number}")

        if context.round_number == 1:
            prompt_lines.append(
                "\nThis is the first round. Introduce the topic "
                "and ask both sides to present their opening arguments."
            )
        else:
            prompt_lines.append("\nPrevious rounds:")
            for r in context.previous_rounds:
                prompt_lines.append(str(r))

            prompt_lines.append(
                "\nAssess the debate so far. Identify areas where "
                "arguments need strengthening and guide both sides "
                "for the next round."
            )

        prompt_lines.append(
            "\nProvide your steer for this round in a concise paragraph."
        )
        return "\n".join(prompt_lines)
