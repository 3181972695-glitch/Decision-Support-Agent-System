"""Tests for the debate API endpoints using FastAPI TestClient.

All LLM calls are mocked at the service level so no real API requests
are made. We replace the DebateService dependency with one that has
a mocked LLMService.
"""

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
    svc.generate = AsyncMock(return_value="Mocked LLM response.")  # type: ignore[method-assign]
    return svc


@pytest.fixture
def test_service(mock_llm: LLMService) -> DebateService:
    repo = InMemoryDebateRepository()
    return DebateService(repository=repo, llm_service=mock_llm)


@pytest.fixture
def client(test_service: DebateService) -> TestClient:
    """Override the debate service dependency with our test instance."""

    def _override() -> DebateService:
        return test_service

    app.dependency_overrides[get_debate_service] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# =================================================================
#  POST /api/debates/
# =================================================================


class TestCreateDebate:
    """POST /api/debates/"""

    def test_creates_debate(self, client: TestClient) -> None:
        resp = client.post("/api/debates/", json={"topic": "Should I learn Rust?"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["topic"] == "Should I learn Rust?"
        assert data["status"] == "pending"
        assert len(data["id"]) > 0
        assert data["rounds"] == []
        assert data["verdict"] is None

    def test_returns_201_for_valid_topic(self, client: TestClient) -> None:
        resp = client.post("/api/debates/", json={"topic": "Test topic"})
        assert resp.status_code == 201

    def test_rejects_empty_topic(self, client: TestClient) -> None:
        resp = client.post("/api/debates/", json={"topic": ""})
        assert resp.status_code == 422

    def test_rejects_missing_topic(self, client: TestClient) -> None:
        resp = client.post("/api/debates/", json={})
        assert resp.status_code == 422

    def test_creates_with_unique_ids(self, client: TestClient) -> None:
        r1 = client.post("/api/debates/", json={"topic": "Topic 1"})
        r2 = client.post("/api/debates/", json={"topic": "Topic 2"})
        assert r1.json()["id"] != r2.json()["id"]


# =================================================================
#  GET /api/debates/{id}
# =================================================================


class TestGetDebate:
    """GET /api/debates/{id}"""

    def test_returns_debate(self, client: TestClient) -> None:
        created = client.post("/api/debates/", json={"topic": "Test"}).json()
        resp = client.get(f"/api/debates/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]
        assert resp.json()["topic"] == "Test"

    def test_returns_404_for_missing(self, client: TestClient) -> None:
        resp = client.get("/api/debates/non-existent-id")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_rounds_empty_initially(self, client: TestClient) -> None:
        created = client.post("/api/debates/", json={"topic": "Test"}).json()
        resp = client.get(f"/api/debates/{created['id']}")
        assert resp.json()["rounds"] == []
        assert resp.status_code == 200


# =================================================================
#  POST /api/debates/{id}/start
# =================================================================


class TestStartDebate:
    """POST /api/debates/{id}/start"""

    def _poll_until_done(
        self, client: TestClient, debate_id: str, timeout: float = 5.0
    ) -> dict:
        """Poll the debate endpoint until status is completed/error, then return it."""
        import time

        deadline = time.time() + timeout
        while time.time() < deadline:
            resp = client.get(f"/api/debates/{debate_id}")
            assert resp.status_code == 200
            data = resp.json()
            if data["status"] in ("completed", "error"):
                return data
            time.sleep(0.1)
        raise TimeoutError(f"Debate {debate_id} did not finish within {timeout}s")

    def test_start_completes_debate(self, client: TestClient) -> None:
        created = client.post("/api/debates/", json={"topic": "Test"}).json()
        resp = client.post(f"/api/debates/{created['id']}/start")
        assert resp.status_code == 200

        # Start returns immediately with IN_PROGRESS — poll for the final result.
        data = self._poll_until_done(client, created["id"])
        assert data["status"] == "completed"
        assert len(data["rounds"]) == 3
        assert data["verdict"] is not None

    def test_start_returns_404_for_missing(self, client: TestClient) -> None:
        resp = client.post("/api/debates/non-existent/start")
        assert resp.status_code == 404

    def test_rounds_have_moderator_and_both_sides(self, client: TestClient) -> None:
        created = client.post("/api/debates/", json={"topic": "Test"}).json()
        client.post(f"/api/debates/{created['id']}/start")
        data = self._poll_until_done(client, created["id"])
        for round_ in data["rounds"]:
            assert round_["moderator_steer"] is not None
            assert round_["pro_argument"] is not None
            assert round_["con_argument"] is not None
            assert round_["pro_argument"]["role"] == "pro"
            assert round_["con_argument"]["role"] == "con"

    def test_verdict_has_summary_and_recommendation(self, client: TestClient) -> None:
        created = client.post("/api/debates/", json={"topic": "Test topic"}).json()
        client.post(f"/api/debates/{created['id']}/start")
        data = self._poll_until_done(client, created["id"])
        assert data["verdict"] is not None
        assert len(data["verdict"]["summary"]) > 0
        assert len(data["verdict"]["recommendation"]) > 0


# =================================================================
#  GET /api/debates/{id}/rounds/{n}
# =================================================================


class TestGetRound:
    """GET /api/debates/{id}/rounds/{n}"""

    def test_returns_round(self, client: TestClient) -> None:
        created = client.post("/api/debates/", json={"topic": "Test"}).json()
        client.post(f"/api/debates/{created['id']}/start")
        resp = client.get(f"/api/debates/{created['id']}/rounds/1")
        assert resp.status_code == 200
        assert resp.json()["round_number"] == 1

    def test_returns_404_for_missing_round(self, client: TestClient) -> None:
        created = client.post("/api/debates/", json={"topic": "Test"}).json()
        resp = client.get(f"/api/debates/{created['id']}/rounds/99")
        assert resp.status_code == 404

    def test_returns_404_for_missing_debate(self, client: TestClient) -> None:
        resp = client.get("/api/debates/non-existent/rounds/1")
        assert resp.status_code == 404


# =================================================================
#  Health check
# =================================================================


class TestHealthCheck:
    """GET /health"""

    def test_health(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
