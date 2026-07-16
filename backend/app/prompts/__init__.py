"""Prompt construction pipeline.

Architecture:
    AgentContext (single source of truth)
        ↓
    PromptBuilder.build(context)
        ↓  returns {"system_prompt", "user_prompt"}
    LLMService.generate()
        ↓
    LLM

Every prompt in the system is built through PromptBuilder.
No other code concatenates prompt strings.
"""

from app.prompts.base import PromptBuilder, format_history

__all__ = ["PromptBuilder", "format_history"]
