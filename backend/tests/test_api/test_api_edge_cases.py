"""Edge-case tests for the debate API endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.debates import get_debate_service
from app.main import app
from app.services.debate_service import DebateService
from app.services.llm_service import LLMService
from app.storage.in_memory import InMemoryDebateRepository


# =================================================================
#  Fixtures
# =================================================================


@pytest.fixture
def mock_llm() -> LLMService:
    svc = LLMService()
    svc.generate = AsyncMock(return_value="Mocked LLM response.")
    return svc


@pytest.fixture
def test_service(mock_llm: LLMService) -> DebateService:
    repo = InMemoryDebateRepository()
    return DebateService(repository=repo, llm_service=mock_llm)


@pytest.fixture
def client(test_service: DebateService) -> TestClient:
    def _override() -> DebateService:
        return test_service

    app.dependency_overrides[get_debate_service] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# =================================================================
#  Edge case tests
# =================================================================


class TestAPICreationEdgeCases:
    """Edge cases for POST /api/debates/"""

    def test_topic_with_special_characters(self, client: TestClient) -> None:
        topics = [
            "Should I buy a house? (Yes/No!)",
            "What about @#$% special chars?",
            "Topic with — em dashes and 'quotes'",
            "Topic with 日本語 Unicode",
            " Topic with leading/trailing spaces ",
        ]
        for topic in topics:
            resp = client.post("/api/debates/", json={"topic": topic})
            assert resp.status_code == 201, f"Failed for topic: {topic}"
            assert resp.json()["topic"] == topic

    def test_very_long_topic(self, client: TestClient) -> None:
        topic = "Should I " + "very " * 100 + "long topic?"
        resp = client.post("/api/debates/", json={"topic": topic[:499]})
        assert resp.status_code == 201
        assert len(resp.json()["topic"]) == 499

    def test_topic_exactly_one_character(self, client: TestClient) -> None:
        resp = client.post("/api/debates/", json={"topic": "A"})
        assert resp.status_code == 201

    def test_topic_at_max_length(self, client: TestClient) -> None:
        topic = "x" * 500
        resp = client.post("/api/debates/", json={"topic": topic})
        assert resp.status_code == 201
        assert len(resp.json()["topic"]) == 500

    def test_topic_exceeds_max_length(self, client: TestClient) -> None:
        topic = "x" * 501
        resp = client.post("/api/debates/", json={"topic": topic})
        assert resp.status_code == 422

    def test_empty_object_body(self, client: TestClient) -> None:
        resp = client.post("/api/debates/", json={})
        assert resp.status_code == 422

    def test_non_string_topic(self, client: TestClient) -> None:
        resp = client.post("/api/debates/", json={"topic": 12345})
        assert resp.status_code == 422

    def test_null_topic(self, client: TestClient) -> None:
        resp = client.post("/api/debates/", json={"topic": None})
        assert resp.status_code == 422


class TestAPIGetEdgeCases:
    """Edge cases for GET /api/debates/{id}"""

    def test_get_nonexistent_id(self, client: TestClient) -> None:
        resp = client.get("/api/debates/nonexistent-id-12345")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_get_debate_immediately_after_create(self, client: TestClient) -> None:
        created = client.post("/api/debates/", json={"topic": "Test"}).json()
        resp = client.get(f"/api/debates/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"
        assert resp.json()["rounds"] == []


class TestAPIStartEdgeCases:
    """Edge cases for POST /api/debates/{id}/start"""

    def test_start_nonexistent_debate(self, client: TestClient) -> None:
        resp = client.post("/api/debates/nonexistent/start")
        assert resp.status_code == 404

    def test_start_twice_returns_in_progress(self, client: TestClient) -> None:
        created = client.post("/api/debates/", json={"topic": "Test"}).json()
        # Start once
        client.post(f"/api/debates/{created['id']}/start")
        # Start again
        resp = client.post(f"/api/debates/{created['id']}/start")
        assert resp.status_code == 200


class TestGetRoundEdgeCases:
    """Edge cases for GET /api/debates/{id}/rounds/{n}"""

    def test_get_round_after_start(self, client: TestClient) -> None:
        created = client.post("/api/debates/", json={"topic": "Test"}).json()
        _ = client.post(f"/api/debates/{created['id']}/start")

        import time

        deadline = time.time() + 5
        while time.time() < deadline:
            data = client.get(f"/api/debates/{created['id']}").json()
            if data["status"] in ("completed", "error"):
                break
            time.sleep(0.2)

        resp = client.get(f"/api/debates/{created['id']}/rounds/1")
        assert resp.status_code == 200
        assert resp.json()["round_number"] == 1

    def test_get_nonexistent_round(self, client: TestClient) -> None:
        created = client.post("/api/debates/", json={"topic": "Test"}).json()
        resp = client.get(f"/api/debates/{created['id']}/rounds/99")
        assert resp.status_code == 404
