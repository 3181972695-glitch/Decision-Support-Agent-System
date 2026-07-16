"""Tests for agent prompt construction and demo mode responses."""

from __future__ import annotations

import pytest

from app.agents.base import AgentContext
from app.agents.con_agent import ConAgent
from app.agents.judge import Judge
from app.agents.moderator import Moderator
from app.agents.pro_agent import ProAgent
from app.domain.debate import Argument, Round
from app.domain.enums import AgentRole, ResponseType
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
                pro_opening=Argument(role=AgentRole.PRO, content="Pro point"),
                con_opening=Argument(role=AgentRole.CON, content="Con point"),
            )
        ]
        ctx = AgentContext(topic="Test", round_number=2, previous_rounds=prev)
        prompt = agent.build_prompt(ctx)
        assert "Pro point" in prompt
        assert "Con point" in prompt

    def test_system_prompt_is_set(self) -> None:
        assert len(ProAgent.SYSTEM_PROMPT) > 0
        assert "FOR" in ProAgent.SYSTEM_PROMPT or "advocate" in ProAgent.SYSTEM_PROMPT

    def test_opening_prompt(self) -> None:
        agent = ProAgent(llm_service=LLMService())
        ctx = AgentContext(
            topic="Test", round_number=1, response_type=ResponseType.OPENING
        )
        prompt = agent.build_prompt(ctx)
        assert "opening argument" in prompt.lower()

    def test_rebuttal_prompt(self) -> None:
        agent = ProAgent(llm_service=LLMService())
        ctx = AgentContext(
            topic="Test",
            round_number=2,
            response_type=ResponseType.REBUTTAL,
            latest_opponent="Con says this is risky.",
        )
        prompt = agent.build_prompt(ctx)
        assert "REBUTTAL" in prompt
        assert "Con says this is risky." in prompt


class TestConAgentPrompts:
    """ConAgent builds prompts with correct content."""

    def test_prompt_includes_topic(self) -> None:
        agent = ConAgent(llm_service=LLMService())
        ctx = AgentContext(topic="Should I invest?", round_number=1)
        prompt = agent.build_prompt(ctx)
        assert "Should I invest?" in prompt
        assert "AGAINST" in prompt
        assert "AGAINST the proposition" in prompt

    def test_system_prompt_is_set(self) -> None:
        assert len(ConAgent.SYSTEM_PROMPT) > 0
        assert (
            "AGAINST" in ConAgent.SYSTEM_PROMPT
            or "challenger" in ConAgent.SYSTEM_PROMPT
        )

    def test_rebuttal_prompt(self) -> None:
        agent = ConAgent(llm_service=LLMService())
        ctx = AgentContext(
            topic="Test",
            round_number=2,
            response_type=ResponseType.REBUTTAL,
            latest_opponent="Pro says this is beneficial.",
        )
        prompt = agent.build_prompt(ctx)
        assert "REBUTTAL" in prompt
        assert "Pro says this is beneficial." in prompt

    def test_cross_examine_ask_prompt(self) -> None:
        agent = ConAgent(llm_service=LLMService())
        ctx = AgentContext(
            topic="Test",
            round_number=1,
            response_type=ResponseType.CROSS_EXAMINE_ASK,
        )
        prompt = agent.build_prompt(ctx)
        assert "concise question" in prompt.lower()


class TestModeratorPrompts:
    """Moderator builds prompts with correct content."""

    def test_intro_prompt(self) -> None:
        agent = Moderator(llm_service=LLMService())
        ctx = AgentContext(
            topic="Test topic",
            round_number=1,
            response_type=ResponseType.MODERATOR_INTRO,
        )
        prompt = agent.build_prompt(ctx)
        assert "round introduction" in prompt.lower()

    def test_summary_prompt(self) -> None:
        agent = Moderator(llm_service=LLMService())
        ctx = AgentContext(
            topic="Test topic",
            round_number=2,
            response_type=ResponseType.MODERATOR_SUMMARY,
        )
        prompt = agent.build_prompt(ctx)
        assert "round summary" in prompt.lower()

    def test_includes_previous_round_content(self) -> None:
        agent = Moderator(llm_service=LLMService())
        prev = [
            Round(
                round_number=1,
                pro_opening=Argument(role=AgentRole.PRO, content="Previous pro point"),
            )
        ]
        ctx = AgentContext(
            topic="Test",
            round_number=2,
            response_type=ResponseType.MODERATOR_INTRO,
            previous_rounds=prev,
        )
        prompt = agent.build_prompt(ctx)
        assert "Previous pro point" in prompt

    def test_get_round_focus(self) -> None:
        from app.agents.moderator import get_round_focus

        assert "core arguments" in get_round_focus(1)
        assert "assumptions" in get_round_focus(2)
        assert "implications" in get_round_focus(3)
        assert "unresolved" in get_round_focus(4)
        assert "unresolved" in get_round_focus(10)


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
                pro_opening=Argument(role=AgentRole.PRO, content=f"Pro {i}"),
                con_opening=Argument(role=AgentRole.CON, content=f"Con {i}"),
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
        assert "Opening Argument" in result
        assert len(result) > 50

    @pytest.mark.asyncio
    async def test_demo_pro_rebuttal(self) -> None:
        _enable_demo()
        ctx = AgentContext(
            topic="Should I learn Rust?",
            round_number=2,
            response_type=ResponseType.REBUTTAL,
        )
        agent = ProAgent(llm_service=LLMService())
        result = await agent.generate(ctx)
        assert "Rebuttal" in result

    @pytest.mark.asyncio
    async def test_demo_con_response(self) -> None:
        _enable_demo()
        ctx = AgentContext(topic="Should I learn Rust?", round_number=1)
        agent = ConAgent(llm_service=LLMService())
        result = await agent.generate(ctx)
        assert "Should I learn Rust?" in result
        assert "Opening Argument" in result

    @pytest.mark.asyncio
    async def test_demo_moderator_response(self) -> None:
        _enable_demo()
        ctx = AgentContext(
            topic="Test",
            round_number=1,
            response_type=ResponseType.MODERATOR_INTRO,
        )
        agent = Moderator(llm_service=LLMService())
        result = await agent.generate(ctx)
        # Should mention the round focus
        assert len(result) > 20

    @pytest.mark.asyncio
    async def test_demo_judge_response(self) -> None:
        _enable_demo()
        ctx = AgentContext(topic="Should I invest?", round_number=4)
        agent = Judge(llm_service=LLMService())
        result = await agent.generate(ctx)
        assert "Should I invest?" in result
        assert "Pro side" in result or "recommendation" in result
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
