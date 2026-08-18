from app.services.knowledge import KnowledgeLoop
from app.services.retriever import RetrievedChunk, context_is_sufficient, reciprocal_rank_fusion


def _chunk(chunk_id: str, text: str, relevance: float, title: str = "Leave Policy") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        text=text,
        title=title,
        url="https://bmihub.burnsmcd.com/leave",
        section="Eligibility",
        relevance=relevance,
        metadata={},
    )


def test_context_is_sufficient_requires_overlap_or_high_score() -> None:
    weak = [_chunk("a", "Office parking map", 0.20)]
    strong = [_chunk("b", "Employees are eligible for annual leave.", 0.91)]
    assert not context_is_sufficient(weak, "How many leave days can I take?")
    assert context_is_sufficient(strong, "How many leave days can I take?")


def test_reciprocal_rank_fusion_merges_lists() -> None:
    vector = [_chunk("v1", "vector hit", 0.8), _chunk("shared", "both", 0.5)]
    keyword = [_chunk("shared", "both", 0.4), _chunk("k1", "keyword hit", 0.7)]
    fused = reciprocal_rank_fusion([vector, keyword])
    assert fused[0].chunk_id == "shared"
    ids = [chunk.chunk_id for chunk in fused]
    assert "v1" in ids and "k1" in ids


class _Discoverer:
    def __init__(self) -> None:
        self.calls = 0

    def discover(self, question: str, *, limit: int = 5) -> list[str]:
        self.calls += 1
        if self.calls == 1:
            return ["https://bmihub.burnsmcd.com/leave"]
        return []


class _Ingestor:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def ingest(self, urls: list[str]) -> int:
        self.urls.extend(urls)
        return len(urls)


def test_knowledge_loop_stops_after_refresh_fills_gap() -> None:
    later = [_chunk("ok", "Annual leave is 20 days.", 0.9)]
    calls = {"n": 0}

    def retrieve(_question: str) -> list[RetrievedChunk]:
        calls["n"] += 1
        return later

    discoverer = _Discoverer()
    ingestor = _Ingestor()
    loop = KnowledgeLoop(discoverer=discoverer, ingestor=ingestor, max_iterations=5)
    result = loop.fill_gaps(
        "How many leave days?",
        [],
        retrieve=retrieve,
        min_relevance=0.28,
    )
    assert result == later
    assert ingestor.urls == ["https://bmihub.burnsmcd.com/leave"]
    assert discoverer.calls == 1


def test_knowledge_loop_stops_when_no_urls() -> None:
    class EmptyDiscoverer:
        def discover(self, question: str, *, limit: int = 5) -> list[str]:
            return []

    loop = KnowledgeLoop(discoverer=EmptyDiscoverer(), ingestor=_Ingestor())
    result = loop.fill_gaps("unknown", [], retrieve=lambda _q: [], min_relevance=0.28)
    assert result == []
