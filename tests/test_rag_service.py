from __future__ import annotations

from app.schemas.chat import ChatRequest, ChatResponse, Source
from app.services.rag import RagDependencies, RagService
from app.services.retriever import RetrievedChunk


class FakeLLM:
    def __init__(self, answer: str = "Based on BMI Hub, wear PPE. Source: Safety Guide.") -> None:
        self.answer = answer
        self.calls: list[dict[str, str]] = []

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        self.calls.append({"system_prompt": system_prompt, "user_prompt": user_prompt})
        return self.answer


class FakeRetriever:
    def __init__(self, chunks: list[RetrievedChunk] | None = None) -> None:
        self.chunks = chunks or []

    def search(self, query: str, *, top_k: int | None = None) -> list[RetrievedChunk]:
        return list(self.chunks)


class BrokenRetriever:
    def search(self, query: str, *, top_k: int | None = None) -> list[RetrievedChunk]:
        raise RuntimeError("chroma down")


def test_rag_service_returns_answer_and_sources() -> None:
    chunks = [
        RetrievedChunk(
            chunk_id="c1",
            text="Wear PPE before entering the site.",
            title="Safety Guide",
            url="https://bmihub.burnsmcd.com/safety",
            section="PPE",
            relevance=0.91,
            metadata={},
        )
    ]
    llm = FakeLLM()
    service = RagService(
        dependencies=RagDependencies(
            embedder=object(),  # type: ignore[arg-type]
            retriever=FakeRetriever(chunks),  # type: ignore[arg-type]
            llm=llm,  # type: ignore[arg-type]
        )
    )

    response = service.chat(ChatRequest(message="What PPE is required?"))

    assert isinstance(response, ChatResponse)
    assert "PPE" in response.answer
    assert len(response.sources) == 1
    assert response.sources[0] == Source(
        title="Safety Guide",
        url="https://bmihub.burnsmcd.com/safety",
        section="PPE",
        relevance=0.91,
    )
    assert "Retrieved BMI Hub passages" in llm.calls[0]["user_prompt"]
    assert "Answer ONLY using" in llm.calls[0]["system_prompt"]


def test_rag_service_handles_empty_retrieval_without_llm() -> None:
    llm = FakeLLM(answer="should not be used")
    service = RagService(
        dependencies=RagDependencies(
            embedder=object(),  # type: ignore[arg-type]
            retriever=FakeRetriever([]),  # type: ignore[arg-type]
            llm=llm,  # type: ignore[arg-type]
        )
    )

    response = service.chat(ChatRequest(message="Unknown topic?"))

    assert "could not find" in response.answer.lower()
    assert response.sources == []
    assert llm.calls == []


def test_rag_service_raises_on_retrieval_failure() -> None:
    from app.services.rag import RagServiceError

    service = RagService(
        dependencies=RagDependencies(
            embedder=object(),  # type: ignore[arg-type]
            retriever=BrokenRetriever(),  # type: ignore[arg-type]
            llm=FakeLLM(),  # type: ignore[arg-type]
        )
    )

    try:
        service.chat(ChatRequest(message="hello"))
        assert False, "expected RagServiceError"
    except RagServiceError as exc:
        assert "retrieve" in str(exc).lower()
