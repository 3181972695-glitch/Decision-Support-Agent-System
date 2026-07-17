"""Tests for Expert Mode."""

from unittest.mock import AsyncMock

import pytest

from app.services.expert_service import ExpertService
from app.services.llm_service import LLMService


@pytest.fixture
def mock_llm() -> LLMService:
    svc = LLMService()
    svc.generate = AsyncMock(return_value="Mocked expert analysis.")
    return svc


@pytest.fixture
def service(mock_llm: LLMService) -> ExpertService:
    return ExpertService(llm_service=mock_llm)


@pytest.mark.asyncio
async def test_unknown_mode_returns_error(service: ExpertService) -> None:
    """Unknown mode should raise ValueError."""
    with pytest.raises(ValueError, match="Unknown expert mode"):
        await service.analyze("nonexistent_mode", "test question")


@pytest.mark.asyncio
async def test_software_mode_returns_correct_structure(service: ExpertService) -> None:
    """Software mode should return 3 experts and a final decision."""
    result = await service.analyze("software", "Should we migrate to microservices?")

    assert result["mode"] == "Software Architecture Expert"
    assert result["question"] == "Should we migrate to microservices?"
    assert len(result["experts"]) == 3

    roles = [e["role"] for e in result["experts"]]
    assert "Architect" in roles
    assert "Security Engineer" in roles
    assert "Performance Engineer" in roles

    for expert in result["experts"]:
        assert "analysis" in expert
        assert len(expert["analysis"]) > 0

    assert "final_decision" in result
    assert len(result["final_decision"]) > 0


@pytest.mark.asyncio
async def test_career_mode_returns_correct_structure(service: ExpertService) -> None:
    """Career mode should return 3 experts and a final decision."""
    result = await service.analyze("career", "Should I learn Rust or Go?")

    assert result["mode"] == "Career Strategy Expert"
    assert len(result["experts"]) == 3

    roles = [e["role"] for e in result["experts"]]
    assert "Career Coach" in roles
    assert "Industry Analyst" in roles
    assert "Hiring Manager" in roles

    assert len(result["final_decision"]) > 0


@pytest.mark.asyncio
async def test_experts_run_in_parallel(service: ExpertService) -> None:
    """All experts should be called, and decision-maker should be called once."""
    result = await service.analyze("software", "Test question?")

    # 3 expert calls + 1 decision-maker call = 4 total
    assert service._llm.generate.await_count == 4  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_list_modes() -> None:
    """list_modes should return available modes."""
    from app.experts.expert_config import list_modes
    modes = list_modes()
    assert "software" in modes
    assert "career" in modes


@pytest.mark.asyncio
async def test_get_mode() -> None:
    """get_mode should return None for unknown modes."""
    from app.experts.expert_config import get_mode
    assert get_mode("software") is not None
    assert get_mode("nonexistent") is None
