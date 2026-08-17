from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.chat import ChatResponse, Source
from app.services.rag import RagServiceError, reset_rag_service


class StubRagService:
    def __init__(self, response: ChatResponse | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error

    def chat(self, request):  # noqa: ANN001
        if self.error:
            raise self.error
        assert request.message
        return self.response


def setup_function() -> None:
    reset_rag_service()
    app.dependency_overrides.clear()


def teardown_function() -> None:
    reset_rag_service()
    app.dependency_overrides.clear()


def test_chat_endpoint_success() -> None:
    from app.services.rag import get_rag_service

    expected = ChatResponse(
        answer="Use the approved checklist.",
        sources=[
            Source(
                title="Checklist",
                url="https://bmihub.burnsmcd.com/checklist",
                section="Overview",
                relevance=0.88,
            )
        ],
    )
    app.dependency_overrides[get_rag_service] = lambda: StubRagService(response=expected)
    client = TestClient(app)

    response = client.post(
        "/api/chat",
        json={"message": "Where is the checklist?", "conversationId": "abc-123"},
    )

    assert response.status_code == 200
    assert response.json() == expected.model_dump()


def test_chat_endpoint_validation_error() -> None:
    client = TestClient(app)
    response = client.post("/api/chat", json={"message": "   "})
    assert response.status_code == 422
    payload = response.json()
    assert payload["detail"] == "Invalid request payload."


def test_chat_endpoint_service_unavailable() -> None:
    from app.services.rag import get_rag_service

    app.dependency_overrides[get_rag_service] = lambda: StubRagService(
        error=RagServiceError("Failed to retrieve relevant BMI Hub content.")
    )
    client = TestClient(app)

    response = client.post("/api/chat", json={"message": "hello"})
    assert response.status_code == 503
    assert "retrieve" in response.json()["detail"].lower()


def test_health_endpoints() -> None:
    client = TestClient(app)
    for path in ("/health", "/api/health"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
