"""Tests for ExpertGeneratorService."""

from unittest.mock import AsyncMock

import pytest

from app.services.expert_generator_service import ExpertGeneratorService
from app.services.llm_service import LLMService


_SAMPLE_EXPERTS_JSON = """[
  {
    "role": "AI Strategy Consultant",
    "expertise": "AI adoption and business impact",
    "system_prompt": "You analyze AI transformation strategy for enterprises."
  },
  {
    "role": "Security Engineer",
    "expertise": "Security and data privacy",
    "system_prompt": "You evaluate security risks of AI adoption."
  },
  {
    "role": "Engineering Manager",
    "expertise": "Software team productivity",
    "system_prompt": "You analyze engineering workflow impact of AI tools."
  }
]"""


@pytest.fixture
def mock_llm() -> LLMService:
    svc = LLMService()
    svc.generate = AsyncMock(return_value=_SAMPLE_EXPERTS_JSON)
    return svc


@pytest.fixture
def service(mock_llm: LLMService) -> ExpertGeneratorService:
    return ExpertGeneratorService(llm_service=mock_llm)


@pytest.mark.asyncio
async def test_generates_three_or_more_experts(service: ExpertGeneratorService) -> None:
    """Should return 3-5 experts for a valid question."""
    result = await service.generate("Should we adopt AI coding agents?")
    assert len(result) >= 3
    assert len(result) <= 5


@pytest.mark.asyncio
async def test_each_expert_has_required_fields(service: ExpertGeneratorService) -> None:
    """Each expert should have role, expertise, and system_prompt."""
    result = await service.generate("Should we adopt AI coding agents?")
    for expert in result:
        assert "role" in expert
        assert "expertise" in expert
        assert "system_prompt" in expert
        assert len(expert["role"].strip()) > 0
        assert len(expert["expertise"].strip()) > 0
        assert len(expert["system_prompt"].strip()) > 0


@pytest.mark.asyncio
async def test_roles_are_unique(service: ExpertGeneratorService) -> None:
    """All generated roles should be unique."""
    result = await service.generate("Should we adopt AI coding agents?")
    roles = [e["role"] for e in result]
    assert len(roles) == len(set(roles)), f"Duplicate roles found: {roles}"


@pytest.mark.asyncio
async def test_expertise_is_relevant_to_role(service: ExpertGeneratorService) -> None:
    """Each expert's expertise should be non-empty and relevant."""
    result = await service.generate("Should we adopt AI coding agents?")
    for expert in result:
        assert len(expert["expertise"]) > 5


@pytest.mark.asyncio
async def test_missing_question_raises_error(service: ExpertGeneratorService) -> None:
    """Empty question should raise ValueError."""
    with pytest.raises(ValueError, match="Question is required"):
        await service.generate("")
    with pytest.raises(ValueError, match="Question is required"):
        await service.generate("   ")


@pytest.mark.asyncio
async def test_invalid_llm_response_raises_error(service: ExpertGeneratorService) -> None:
    """Non-JSON LLM response should raise ValueError."""
    service._llm.generate = AsyncMock(return_value="This is not JSON")
    with pytest.raises(ValueError, match="No JSON array found"):
        await service.generate("Test?")


@pytest.mark.asyncio
async def test_json_in_code_fence_is_parsed(mock_llm: LLMService) -> None:
    """JSON wrapped in markdown code fences should be parsed correctly."""
    svc = LLMService()
    svc.generate = AsyncMock(return_value=f"```json\n{_SAMPLE_EXPERTS_JSON}\n```")
    gen = ExpertGeneratorService(llm_service=svc)
    result = await gen.generate("Test?")
    assert len(result) == 3
    assert result[0]["role"] == "AI Strategy Consultant"
