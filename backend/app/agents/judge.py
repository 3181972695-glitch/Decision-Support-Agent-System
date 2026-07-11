"""Judge Agent — renders final verdict after all rounds."""

from app.agents.base import AgentContext, BaseAgent
from app.agents.registry import AgentRegistry


@AgentRegistry.register("judge")
class Judge(BaseAgent):
    """Impartial judge that summarises and recommends."""

    SYSTEM_PROMPT = (
        "You are an impartial and wise judge. "
        "Your role is to carefully review all arguments from both sides, "
        "summarise the key points, and provide a clear, actionable "
        "final recommendation to the user. "
        "Be balanced, fair, and practical."
    )

    def build_prompt(self, context: AgentContext) -> str:
        prompt_lines = [f"Debate topic: {context.topic}"]
        prompt_lines.append("\nComplete debate history:")

        for r in context.previous_rounds:
            prompt_lines.append(str(r))

        prompt_lines.append(
            "\nPlease provide:\n"
            "1. A balanced summary of the key arguments from both sides.\n"
            "2. An assessment of the strongest points from each side.\n"
            "3. A clear final recommendation for the user."
        )
        return "\n".join(prompt_lines)
