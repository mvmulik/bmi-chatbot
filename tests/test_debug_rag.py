from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_debug_rag_endpoint_safe_shape() -> None:
    client = TestClient(app)
    response = client.get("/api/debug/rag")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"healthy", "unhealthy"}
    assert "chroma_path" in payload
    assert "collection_exists" in payload
    assert "collection_name" in payload
    assert "document_count" in payload
    assert "embedding_configured" in payload
    assert "llm_configured" in payload
    blob = response.text.lower()
    assert "api_key" not in blob or "configured" in blob
    assert "sk-" not in blob
    assert "password" not in blob
    assert "bearer " not in blob


def test_debug_search_endpoint_shape() -> None:
    client = TestClient(app)
    response = client.get("/api/debug/search", params={"q": "test"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "test"
    assert "result_count" in payload
    assert "results" in payload
    assert isinstance(payload["results"], list)
