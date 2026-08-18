from __future__ import annotations

from app.schemas.chat import ChatRequest, ChatResponse
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
    assert response.sources[0].title == "Safety Guide"
    assert response.sources[0].url == "https://bmihub.burnsmcd.com/safety"
    assert response.sources[0].section == "PPE"
    assert response.sources[0].relevance == 0.91
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

    assert "couldn" in response.answer.lower()
    assert "bmi hub" in response.answer.lower()
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


def test_rag_service_uses_previous_turn_for_follow_up() -> None:
    from app.services.conversation import ConversationStore

    chunks = [
        RetrievedChunk(
            chunk_id="c1",
            text="Eligible employees receive 22 days of annual leave.",
            title="Leave Policy",
            url="https://bmihub.burnsmcd.com/leave",
            section="Entitlement",
            relevance=0.93,
            metadata={},
        )
    ]
    llm = FakeLLM(answer="22 days. Source: Leave Policy.")
    conversations = ConversationStore()
    conversations.add("conv-1", "What is the leave policy?", "Annual leave is described on BMI Hub.")
    service = RagService(
        dependencies=RagDependencies(
            embedder=object(),  # type: ignore[arg-type]
            retriever=FakeRetriever(chunks),  # type: ignore[arg-type]
            llm=llm,  # type: ignore[arg-type]
            conversations=conversations,
        )
    )

    service.chat(ChatRequest(message="How many days can I take?", conversation_id="conv-1"))
    assert "previous question" in llm.calls[0]["user_prompt"].lower()
    assert "leave policy" in llm.calls[0]["user_prompt"].lower()


def test_rag_service_indexes_then_answers_after_knowledge_loop() -> None:
    later = [
        RetrievedChunk(
            chunk_id="c2",
            text="Annual leave is described on BMI Hub.",
            title="Leave Policy",
            url="https://bmihub.burnsmcd.com/leave",
            section="Eligibility",
            relevance=0.88,
            metadata={},
        )
    ]

    class FillingRetriever:
        def __init__(self) -> None:
            self.calls = 0

        def search(self, query: str, *, top_k: int | None = None) -> list[RetrievedChunk]:
            self.calls += 1
            return later if self.calls > 1 else []

    class Discoverer:
        def discover(self, question: str, *, limit: int = 5) -> list[str]:
            return ["https://bmihub.burnsmcd.com/leave"]

    class Ingestor:
        def ingest(self, urls: list[str]) -> int:
            return len(urls)

    from app.services.knowledge import KnowledgeLoop

    llm = FakeLLM(answer="According to BMI Hub Leave Policy, annual leave is described.")
    retriever = FillingRetriever()
    service = RagService(
        dependencies=RagDependencies(
            embedder=object(),  # type: ignore[arg-type]
            retriever=retriever,  # type: ignore[arg-type]
            llm=llm,  # type: ignore[arg-type]
            knowledge_loop=KnowledgeLoop(discoverer=Discoverer(), ingestor=Ingestor()),
        )
    )
    response = service.chat(ChatRequest(message="What is the leave policy?"))
    assert "leave" in response.answer.lower()
    assert retriever.calls == 2
    assert response.sources[0].title == "Leave Policy"
