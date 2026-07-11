"""Tests for agent prompt construction and demo mode responses."""

from __future__ import annotations

import pytest

from app.agents.base import AgentContext
from app.agents.con_agent import ConAgent
from app.agents.judge import Judge
from app.agents.moderator import Moderator
from app.agents.pro_agent import ProAgent
from app.domain.debate import Argument, Round
from app.domain.enums import AgentRole
from app.services.llm_service import LLMService


# =================================================================
#  Fixtures
# =================================================================


@pytest.fixture(autouse=True)
def _reset_demo_mode() -> None:
    """Ensure DEMO_MODE is reset after each test."""
    from app.config import settings

    yield
    settings.DEMO_MODE = False


def _enable_demo() -> None:
    """Enable demo mode for the current test."""
    from app.config import settings

    settings.DEMO_MODE = True


# =================================================================
#  Agent prompt structure
# =================================================================


class TestProAgentPrompts:
    """ProAgent builds prompts with correct content."""

    def test_prompt_includes_topic(self) -> None:
        agent = ProAgent(llm_service=LLMService())
        ctx = AgentContext(topic="Should I travel?", round_number=1)
        prompt = agent.build_prompt(ctx)
        assert "Should I travel?" in prompt
        assert "FOR" in prompt
        assert "Round: 1" in prompt

    def test_prompt_includes_moderator_steer(self) -> None:
        agent = ProAgent(llm_service=LLMService())
        ctx = AgentContext(
            topic="Test topic", round_number=2, moderator_steer="Focus on cost."
        )
        prompt = agent.build_prompt(ctx)
        assert "Focus on cost." in prompt

    def test_prompt_includes_previous_rounds(self) -> None:
        agent = ProAgent(llm_service=LLMService())
        prev = [
            Round(
                round_number=1,
                pro_argument=Argument(role=AgentRole.PRO, content="Pro point"),
                con_argument=Argument(role=AgentRole.CON, content="Con point"),
            )
        ]
        ctx = AgentContext(topic="Test", round_number=2, previous_rounds=prev)
        prompt = agent.build_prompt(ctx)
        assert "Pro point" in prompt
        assert "Con point" in prompt

    def test_system_prompt_is_set(self) -> None:
        assert len(ProAgent.SYSTEM_PROMPT) > 0
        assert "FOR" in ProAgent.SYSTEM_PROMPT or "advocate" in ProAgent.SYSTEM_PROMPT


class TestConAgentPrompts:
    """ConAgent builds prompts with correct content."""

    def test_prompt_includes_topic(self) -> None:
        agent = ConAgent(llm_service=LLMService())
        ctx = AgentContext(topic="Should I invest?", round_number=1)
        prompt = agent.build_prompt(ctx)
        assert "Should I invest?" in prompt
        assert "AGAINST" in prompt
        assert "NOT pursue" in prompt

    def test_system_prompt_is_set(self) -> None:
        assert len(ConAgent.SYSTEM_PROMPT) > 0
        assert (
            "AGAINST" in ConAgent.SYSTEM_PROMPT
            or "challenger" in ConAgent.SYSTEM_PROMPT
        )


class TestModeratorPrompts:
    """Moderator builds prompts with correct content."""

    def test_first_round_prompt(self) -> None:
        agent = Moderator(llm_service=LLMService())
        ctx = AgentContext(topic="Test topic", round_number=1)
        prompt = agent.build_prompt(ctx)
        assert "first round" in prompt.lower()
        assert "introduce" in prompt.lower()

    def test_later_round_prompt(self) -> None:
        agent = Moderator(llm_service=LLMService())
        ctx = AgentContext(topic="Test topic", round_number=2)
        prompt = agent.build_prompt(ctx)
        assert "previous rounds" in prompt.lower() or "Previous rounds" in prompt
        assert "guide" in prompt.lower()

    def test_includes_previous_round_content(self) -> None:
        agent = Moderator(llm_service=LLMService())
        prev = [
            Round(
                round_number=1,
                pro_argument=Argument(role=AgentRole.PRO, content="Previous pro point"),
            )
        ]
        ctx = AgentContext(topic="Test", round_number=2, previous_rounds=prev)
        prompt = agent.build_prompt(ctx)
        assert "Previous pro point" in prompt


class TestJudgePrompts:
    """Judge builds prompts with correct content."""

    def test_prompt_includes_topic(self) -> None:
        agent = Judge(llm_service=LLMService())
        ctx = AgentContext(topic="Should I move?", round_number=4)
        prompt = agent.build_prompt(ctx)
        assert "Should I move?" in prompt
        assert "summary" in prompt.lower()
        assert "recommendation" in prompt.lower()

    def test_prompt_includes_all_rounds(self) -> None:
        agent = Judge(llm_service=LLMService())
        rounds = [
            Round(
                round_number=i,
                pro_argument=Argument(role=AgentRole.PRO, content=f"Pro {i}"),
                con_argument=Argument(role=AgentRole.CON, content=f"Con {i}"),
            )
            for i in range(1, 4)
        ]
        ctx = AgentContext(topic="Test", round_number=4, previous_rounds=rounds)
        prompt = agent.build_prompt(ctx)
        for i in range(1, 4):
            assert f"Pro {i}" in prompt
            assert f"Con {i}" in prompt


# =================================================================
#  Agent generation (demo mode)
# =================================================================


class TestDemoMode:
    """Demo mode returns role-appropriate simulated responses."""

    @pytest.mark.asyncio
    async def test_demo_pro_response(self) -> None:
        _enable_demo()
        ctx = AgentContext(topic="Should I learn Rust?", round_number=1)
        agent = ProAgent(llm_service=LLMService())
        result = await agent.generate(ctx)
        assert "Should I learn Rust?" in result
        assert "Career Advancement" in result or "Opening Argument" in result
        assert len(result) > 50

    @pytest.mark.asyncio
    async def test_demo_con_response(self) -> None:
        _enable_demo()
        ctx = AgentContext(topic="Should I learn Rust?", round_number=1)
        agent = ConAgent(llm_service=LLMService())
        result = await agent.generate(ctx)
        assert "Should I learn Rust?" in result
        assert "Significant Investment" in result or "Opening Argument" in result

    @pytest.mark.asyncio
    async def test_demo_moderator_response(self) -> None:
        _enable_demo()
        ctx = AgentContext(topic="Test", round_number=1)
        agent = Moderator(llm_service=LLMService())
        result = await agent.generate(ctx)
        assert "Round 1" in result or "Steer for Round" in result

    @pytest.mark.asyncio
    async def test_demo_judge_response(self) -> None:
        _enable_demo()
        ctx = AgentContext(topic="Should I invest?", round_number=4)
        agent = Judge(llm_service=LLMService())
        result = await agent.generate(ctx)
        assert "Should I invest?" in result
        assert "Verdict" in result or "Pro side" in result or "recommendation" in result
        assert len(result) > 100

    @pytest.mark.asyncio
    async def test_demo_round_progression(self) -> None:
        """Each round of pro demo returns different content."""
        _enable_demo()
        agent = ProAgent(llm_service=LLMService())
        results = []
        for r in range(1, 4):
            ctx = AgentContext(topic="Test", round_number=r)
            results.append(await agent.generate(ctx))

        assert results[0] != results[1]
        assert results[1] != results[2]

    @pytest.mark.asyncio
    async def test_demo_fallback_response(self) -> None:
        """When the role can't be determined, a generic response is returned."""
        _enable_demo()
        from app.services.llm_service import LLMService as Svc

        svc = Svc()
        result = await svc.generate(prompt="Some generic text without role hints.")
        assert result and len(result) > 0
        assert "decision" in result.lower()
