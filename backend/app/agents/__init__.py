"""Agent implementations — each file registers itself via @AgentRegistry.register."""

# Import all agent modules so their @AgentRegistry.register decorators run.
# Each agent class auto-registers on module import.
from app.agents import base, con_agent, judge, moderator, pro_agent, registry

__all__ = [
    "base",
    "con_agent",
    "judge",
    "moderator",
    "pro_agent",
    "registry",
]
