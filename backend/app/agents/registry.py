"""Agent registry — maps role names to agent classes.

New agents can register themselves with the @AgentRegistry.register decorator,
making them discoverable by role without modifying any service code.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.agents.base import BaseAgent


class AgentRegistry:
    """Central registry mapping agent roles to their classes."""

    _registry: dict[str, type[BaseAgent]] = {}

    @classmethod
    def register(cls, role: str) -> Any:
        """Decorator: register an agent class under the given role.

        Usage:
            @AgentRegistry.register("pro")
            class ProAgent(BaseAgent):
                ...
        """

        def decorator(agent_cls: type[BaseAgent]) -> type[BaseAgent]:
            cls._registry[role] = agent_cls
            return agent_cls

        return decorator

    @classmethod
    def get(cls, role: str) -> type[BaseAgent]:
        """Retrieve the agent class for a given role."""
        if role not in cls._registry:
            raise KeyError(
                f"Unknown agent role: '{role}'. Available: {list(cls._registry)}"
            )
        return cls._registry[role]

    @classmethod
    def get_role_for_agent(cls, agent_cls: type[BaseAgent]) -> str | None:
        """Reverse lookup: find the role name registered for an agent class."""
        for role, cls in cls._registry.items():
            if cls is agent_cls:
                return role
        return None

    @classmethod
    def list_roles(cls) -> list[str]:
        """Return all registered agent role names."""
        return list(cls._registry)
