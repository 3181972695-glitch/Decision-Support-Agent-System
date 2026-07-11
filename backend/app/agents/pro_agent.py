"""Pro Agent — argues in favour of the debate topic."""

from app.agents.base import AgentContext, BaseAgent
from app.agents.registry import AgentRegistry


@AgentRegistry.register("pro")
class ProAgent(BaseAgent):
    """Persuasive agent arguing FOR the topic."""

    SYSTEM_PROMPT = (
        "You are a persuasive and well-reasoned advocate. "
        "Your role is to argue FOR the given decision topic. "
        "Present 3-4 logical, evidence-backed points. "
        "Be constructive, respectful, and convincing."
    )

    def build_prompt(self, context: AgentContext) -> str:
        prompt_lines = [f"Debate topic: {context.topic}"]
        prompt_lines.append(f"Round: {context.round_number}")
        prompt_lines.append("Your position: FOR")

        if context.moderator_steer:
            prompt_lines.append(f"\nModerator's steer: {context.moderator_steer}")

        if context.previous_rounds:
            prompt_lines.append("\nPrevious round context:")
            for r in context.previous_rounds:
                prompt_lines.append(str(r))

        prompt_lines.append(
            "\nConstruct your argument for why the user should pursue this decision."
        )
        return "\n".join(prompt_lines)
