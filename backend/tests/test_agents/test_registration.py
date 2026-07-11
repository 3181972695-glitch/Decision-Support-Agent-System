"""Tests that all agents are properly registered and discoverable."""

from __future__ import annotations

from app.agents.registry import AgentRegistry


class TestAgentRegistration:
    """All four agents should register themselves on import."""

    def test_all_roles_are_registered(self) -> None:
        roles = AgentRegistry.list_roles()
        assert "pro" in roles
        assert "con" in roles
        assert "moderator" in roles
        assert "judge" in roles

    def test_get_returns_agent_class(self) -> None:
        from app.agents.base import BaseAgent

        for role in ("pro", "con", "moderator", "judge"):
            cls = AgentRegistry.get(role)
            assert issubclass(cls, BaseAgent)
            assert len(cls.SYSTEM_PROMPT) > 0

    def test_unknown_role_raises_key_error(self) -> None:
        import pytest

        with pytest.raises(KeyError):
            AgentRegistry.get("nonexistent_role")

    def test_registered_agents_have_unique_names(self) -> None:
        roles = AgentRegistry.list_roles()
        assert len(roles) == len(set(roles)), "Duplicate agent roles detected"
