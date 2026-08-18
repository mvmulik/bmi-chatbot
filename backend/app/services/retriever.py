from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

import chromadb

from app.config import Settings, settings
from app.services.embeddings import EmbeddingProvider

logger = logging.getLogger(__name__)

STOPWORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "of",
    "for",
    "to",
    "in",
    "on",
    "at",
    "is",
    "are",
    "was",
    "were",
    "be",
    "can",
    "i",
    "my",
    "me",
    "we",
    "our",
    "you",
    "your",
    "what",
    "which",
    "who",
    "whom",
    "how",
    "where",
    "when",
    "why",
    "do",
    "does",
    "did",
    "please",
    "tell",
    "about",
    "from",
    "with",
    "this",
    "that",
    "it",
}


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    text: str
    title: str
    url: str
    section: str
    relevance: float
    metadata: dict[str, Any]


def extract_query_terms(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9][a-z0-9-]{2,}", (text or "").lower())
    seen: set[str] = set()
    terms: list[str] = []
    for token in tokens:
        if token in STOPWORDS or token in seen:
            continue
        seen.add(token)
        terms.append(token)
    return terms


def _distance_to_relevance(distance: float | None) -> float:
    if distance is None:
        return 0.0
    relevance = 1.0 - float(distance)
    return max(0.0, min(1.0, relevance))


def _authorized_metadata(metadata: dict[str, Any] | None) -> bool:
    """Keep only content collected under an authorized BMI Hub session."""
    access = str((metadata or {}).get("access") or "authenticated").strip().lower()
    return access in {"authenticated", "authorized"}


def _chunk_from_row(
    *,
    chunk_id: str,
    document: str,
    metadata: dict[str, Any] | None,
    distance: float | None,
) -> RetrievedChunk:
    metadata = metadata or {}
    return RetrievedChunk(
        chunk_id=str(chunk_id),
        text=str(document or ""),
        title=str(metadata.get("page_title") or metadata.get("title") or "BMI Hub"),
        url=str(metadata.get("url") or ""),
        section=str(metadata.get("section") or metadata.get("heading") or ""),
        relevance=_distance_to_relevance(distance),
        metadata=dict(metadata),
    )


def reciprocal_rank_fusion(
    ranked_lists: list[list[RetrievedChunk]],
    *,
    k: int = 60,
) -> list[RetrievedChunk]:
    scores: dict[str, float] = {}
    by_id: dict[str, RetrievedChunk] = {}
    for ranked in ranked_lists:
        for rank, chunk in enumerate(ranked):
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + 1.0 / (k + rank + 1)
            current = by_id.get(chunk.chunk_id)
            if current is None or chunk.relevance > current.relevance:
                by_id[chunk.chunk_id] = chunk

    fused: list[RetrievedChunk] = []
    for chunk_id, score in sorted(scores.items(), key=lambda item: item[1], reverse=True):
        chunk = by_id[chunk_id]
        fused.append(
            RetrievedChunk(
                chunk_id=chunk.chunk_id,
                text=chunk.text,
                title=chunk.title,
                url=chunk.url,
                section=chunk.section,
                relevance=min(1.0, max(chunk.relevance, score)),
                metadata=chunk.metadata,
            )
        )
    return fused


def context_is_sufficient(
    chunks: list[RetrievedChunk],
    question: str,
    *,
    min_relevance: float = 0.28,
) -> bool:
    if not chunks:
        return False
    best = max(chunk.relevance for chunk in chunks)
    if best < min_relevance:
        return False
    terms = extract_query_terms(question)
    if not terms:
        return True
    blob = " ".join(f"{chunk.title} {chunk.section} {chunk.text}" for chunk in chunks).lower()
    hits = sum(1 for term in terms if term in blob)
    if best >= 0.55:
        return True
    return hits >= max(1, min(2, (len(terms) + 1) // 2))


class ChromaRetriever:
    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        config: Settings | None = None,
    ) -> None:
        self.config = config or settings
        self.embedding_provider = embedding_provider
        self.config.chroma_path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(self.config.chroma_path))
        logger.info(
            "Retriever connected to Chroma at %s (collection=%s)",
            self.config.chroma_path,
            self.config.chroma_collection_name,
        )

    def _collection(self):
        return self._client.get_or_create_collection(
            name=self.config.chroma_collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def count(self) -> int:
        return self._collection().count()

    def _vector_search(self, query: str, *, top_k: int) -> list[RetrievedChunk]:
        collection = self._collection()
        count = collection.count()
        if count == 0:
            return []
        query_embedding = self.embedding_provider.embed_query(query)
        result = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, count),
            include=["documents", "metadatas", "distances"],
        )
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        ids = (result.get("ids") or [[]])[0]
        chunks: list[RetrievedChunk] = []
        for index, doc in enumerate(documents):
            metadata = metadatas[index] if index < len(metadatas) else {}
            distance = distances[index] if index < len(distances) else None
            chunk_id = ids[index] if index < len(ids) else str((metadata or {}).get("chunk_id", ""))
            chunks.append(
                _chunk_from_row(
                    chunk_id=str(chunk_id),
                    document=str(doc or ""),
                    metadata=metadata if isinstance(metadata, dict) else {},
                    distance=distance,
                )
            )
        return chunks

    def _keyword_search(self, query: str, *, top_k: int) -> list[RetrievedChunk]:
        terms = extract_query_terms(query)
        if not terms:
            return []
        collection = self._collection()
        if collection.count() == 0:
            return []

        found: dict[str, RetrievedChunk] = {}
        for term in terms[:4]:
            try:
                result = collection.get(
                    where_document={"$contains": term},
                    include=["documents", "metadatas"],
                    limit=top_k,
                )
            except TypeError:
                result = collection.get(
                    where_document={"$contains": term},
                    include=["documents", "metadatas"],
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("Keyword search skipped for term=%s (%s)", term, exc)
                continue
            documents = result.get("documents") or []
            metadatas = result.get("metadatas") or []
            ids = result.get("ids") or []
            for index, doc in enumerate(documents[:top_k]):
                metadata = metadatas[index] if index < len(metadatas) else {}
                chunk_id = ids[index] if index < len(ids) else str((metadata or {}).get("chunk_id", ""))
                title = str((metadata or {}).get("page_title") or "")
                blob = f"{title} {doc}".lower()
                overlap = sum(1 for item in terms if item in blob)
                relevance = min(1.0, 0.35 + 0.15 * overlap)
                if title and title.lower() in query.lower():
                    relevance = min(1.0, relevance + 0.2)
                found[str(chunk_id)] = _chunk_from_row(
                    chunk_id=str(chunk_id),
                    document=str(doc or ""),
                    metadata=metadata if isinstance(metadata, dict) else {},
                    distance=1.0 - relevance,
                )
        ranked = sorted(found.values(), key=lambda chunk: chunk.relevance, reverse=True)
        return ranked[:top_k]

    def search(self, query: str, *, top_k: int | None = None) -> list[RetrievedChunk]:
        k = top_k or self.config.rag_top_k
        vector_k = max(k, self.config.rag_hybrid_candidate_k)
        vector_chunks = self._vector_search(query, top_k=vector_k)
        keyword_chunks = self._keyword_search(query, top_k=vector_k) if self.config.rag_hybrid_search else []
        if keyword_chunks:
            fused = reciprocal_rank_fusion([vector_chunks, keyword_chunks])
        else:
            fused = vector_chunks

        fused = [chunk for chunk in fused if _authorized_metadata(chunk.metadata)]

        query_lower = query.lower()
        fused.sort(
            key=lambda chunk: (
                1 if chunk.title and chunk.title.lower() in query_lower else 0,
                chunk.relevance,
            ),
            reverse=True,
        )
        logger.info(
            "Retrieved %s chunks (vector=%s keyword=%s hybrid=%s)",
            min(k, len(fused)),
            len(vector_chunks),
            len(keyword_chunks),
            bool(keyword_chunks),
        )
        return fused[:k]
