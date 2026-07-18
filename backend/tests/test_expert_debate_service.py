"""Tests for ExpertDebateService."""

from unittest.mock import AsyncMock

import pytest

from app.services.expert_debate_service import ExpertDebateService
from app.services.llm_service import LLMService


@pytest.fixture
def mock_llm() -> LLMService:
    svc = LLMService()
    svc.generate = AsyncMock(
        return_value="Some analysis here.\nARGUMENTS:scalability|security|cost"
    )
    return svc


@pytest.fixture
def service(mock_llm: LLMService) -> ExpertDebateService:
    return ExpertDebateService(llm_service=mock_llm)


@pytest.mark.asyncio
async def test_unknown_mode_returns_error(service: ExpertDebateService) -> None:
    """Unknown mode should raise ValueError."""
    with pytest.raises(ValueError, match="Unknown expert mode"):
        await service.debate("nonexistent", "test question")


@pytest.mark.asyncio
async def test_software_mode_returns_correct_structure(service: ExpertDebateService) -> None:
    """Software mode should return 3 experts, debate rounds, and final decision."""
    result = await service.debate("software", "Should we migrate to microservices?")

    assert result["mode"] == "Software Architecture Expert Debate"
    assert result["question"] == "Should we migrate to microservices?"
    assert len(result["experts"]) == 3

    roles = [e["role"] for e in result["experts"]]
    assert "Architect" in roles
    assert "Security Engineer" in roles
    assert "Performance Engineer" in roles

    for expert in result["experts"]:
        assert "analysis" in expert
        assert "arguments" in expert
        assert len(expert["analysis"]) > 0

    # 3 experts × 2 others each = 6 debate rounds
    assert len(result["debate_rounds"]) == 6

    assert "final_decision" in result
    assert len(result["final_decision"]) > 0
    assert isinstance(result["confidence"], int)
    assert 0 <= result["confidence"] <= 100


@pytest.mark.asyncio
async def test_career_mode_returns_correct_structure(service: ExpertDebateService) -> None:
    """Career mode should return 3 experts and full structure."""
    result = await service.debate("career", "Should I learn Rust or Go?")

    assert result["mode"] == "Career Strategy Expert Debate"
    assert len(result["experts"]) == 3

    roles = [e["role"] for e in result["experts"]]
    assert "Career Coach" in roles
    assert "Industry Analyst" in roles
    assert "Hiring Manager" in roles

    # 3 experts × 2 others each = 6 debate rounds
    assert len(result["debate_rounds"]) == 6
    assert len(result["final_decision"]) > 0


@pytest.mark.asyncio
async def test_parallel_execution_count(service: ExpertDebateService) -> None:
    """Verify the correct number of LLM calls:
    - Phase 1: 3 expert analyses
    - Phase 2: 6 cross-critiques (3 experts × 2 others)
    - Phase 3: 1 judge
    Total = 10
    """
    await service.debate("software", "Test?")

    # 3 + 6 + 1 = 10 calls
    assert service._llm.generate.await_count == 10  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_debate_round_roles_are_correct(service: ExpertDebateService) -> None:
    """Each debate round should have a unique speaker → target pair."""
    result = await service.debate("software", "Test?")

    pairs = [(dr["speaker"], dr["response_to"]) for dr in result["debate_rounds"]]
    assert len(pairs) == 6

    expected_pairs = [
        ("Architect", "Security Engineer"),
        ("Architect", "Performance Engineer"),
        ("Security Engineer", "Architect"),
        ("Security Engineer", "Performance Engineer"),
        ("Performance Engineer", "Architect"),
        ("Performance Engineer", "Security Engineer"),
    ]
    for pair in expected_pairs:
        assert pair in pairs, f"Missing debate pair: {pair}"


@pytest.mark.asyncio
async def test_expert_arguments_are_extracted(service: ExpertDebateService) -> None:
    """Expert responses should have ARGUMENTS parsed into the arguments list."""
    result = await service.debate("software", "Test?")

    for expert in result["experts"]:
        assert len(expert["arguments"]) > 0
        # Our mock returns "scalability|security|cost"
        assert len(expert["arguments"]) == 3


@pytest.mark.asyncio
async def test_judge_confidence_is_parsed(service: ExpertDebateService) -> None:
    """Override mock for judge to return structured output, verify parsing."""
    # For this test, simulate a structured judge response
    async def judge_side_effect(*, system_prompt: str = "", prompt: str, **kwargs: object) -> str:
        if "judge" in prompt.lower() or "trad" in prompt.lower():
            return (
                "After reviewing all perspectives, I recommend a phased migration.\n"
                "FINAL:Proceed with a phased migration starting with the billing module\n"
                "CONFIDENCE:78\n"
                "TRADEOFFS:coupling vs autonomy|security perimeter expansion|team coordination overhead"
            )
        return "Some analysis.\nARGUMENTS:a|b|c"

    svc = LLMService()
    svc.generate = AsyncMock(side_effect=judge_side_effect)
    svc_local = ExpertDebateService(llm_service=svc)

    result = await svc_local.debate("software", "Test?")
    assert result["confidence"] == 78
    assert len(result["key_tradeoffs"]) == 3
    assert "final_decision" in result
    assert len(result["final_decision"]) > 0
