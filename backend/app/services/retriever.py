from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import chromadb

from app.config import Settings, settings
from app.services.embeddings import EmbeddingProvider

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    text: str
    title: str
    url: str
    section: str
    relevance: float
    metadata: dict[str, Any]


def _distance_to_relevance(distance: float | None) -> float:
    if distance is None:
        return 0.0
    # Cosine distance in Chroma: lower is better. Clamp to [0, 1].
    relevance = 1.0 - float(distance)
    return max(0.0, min(1.0, relevance))


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

    def search(self, query: str, *, top_k: int | None = None) -> list[RetrievedChunk]:
        k = top_k or self.config.rag_top_k
        collection = self._collection()
        if collection.count() == 0:
            logger.warning("Chroma collection is empty; no chunks to retrieve.")
            return []

        query_embedding = self.embedding_provider.embed_query(query)
        result = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(k, collection.count()),
            include=["documents", "metadatas", "distances"],
        )

        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        ids = (result.get("ids") or [[]])[0]

        chunks: list[RetrievedChunk] = []
        for index, doc in enumerate(documents):
            metadata = metadatas[index] if index < len(metadatas) else {}
            metadata = metadata or {}
            distance = distances[index] if index < len(distances) else None
            chunk_id = ids[index] if index < len(ids) else str(metadata.get("chunk_id", ""))
            chunks.append(
                RetrievedChunk(
                    chunk_id=str(chunk_id),
                    text=str(doc or ""),
                    title=str(metadata.get("page_title") or metadata.get("title") or "BMI Hub"),
                    url=str(metadata.get("url") or ""),
                    section=str(metadata.get("section") or metadata.get("heading") or ""),
                    relevance=_distance_to_relevance(distance),
                    metadata=dict(metadata),
                )
            )

        logger.info("Retrieved %s chunks for query", len(chunks))
        return chunks
