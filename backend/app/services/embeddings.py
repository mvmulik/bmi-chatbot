from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Sequence

from openai import AzureOpenAI, OpenAI

from app.config import Settings, settings

logger = logging.getLogger(__name__)


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        raise NotImplementedError

    @abstractmethod
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        raise NotImplementedError


class OpenAICompatibleEmbeddingProvider(EmbeddingProvider):
    def __init__(self, config: Settings | None = None) -> None:
        self.config = config or settings
        api_key = self.config.embedding_api_key
        api_base = self.config.embedding_api_base
        api_version = self.config.embedding_api_version
        if not api_key:
            raise ValueError(
                "OPENAI_EMBEDDING_API_KEY or OPENAI_API_KEY is required for embeddings."
            )

        api_type = self.config.openai_api_type.lower()
        if api_type == "azure":
            if not api_base:
                raise ValueError(
                    "OPENAI_EMBEDDING_API_BASE or OPENAI_API_BASE is required for Azure embeddings."
                )
            if not self.config.embedding_model:
                raise ValueError(
                    "OPENAI_EMBEDDING_DEPLOYMENT_NAME is required for Azure embeddings."
                )
            self._client: AzureOpenAI | OpenAI = AzureOpenAI(
                api_key=api_key,
                api_version=api_version,
                azure_endpoint=api_base,
            )
        else:
            self._client = OpenAI(
                api_key=api_key,
                base_url=api_base or None,
            )
        self._model = self.config.embedding_model
        logger.info("Chat embedding provider ready (type=%s, model=%s)", api_type, self._model)

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self._client.embeddings.create(model=self._model, input=list(texts))
        ordered = sorted(response.data, key=lambda item: item.index)
        return [list(item.embedding) for item in ordered]

    def embed_query(self, text: str) -> list[float]:
        vectors = self.embed_documents([text])
        return vectors[0]


class HashEmbeddingProvider(EmbeddingProvider):
    """Deterministic embeddings for offline tests."""

    def __init__(self, dimensions: int = 32) -> None:
        self._dimensions = dimensions

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            values = [0.0] * self._dimensions
            for index, char in enumerate(text.encode("utf-8")):
                values[index % self._dimensions] += (char % 31) / 31.0
            norm = sum(v * v for v in values) ** 0.5 or 1.0
            vectors.append([v / norm for v in values])
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def create_embedding_provider(config: Settings | None = None) -> EmbeddingProvider:
    cfg = config or settings
    provider = (cfg.embedding_provider or "").strip().lower()
    if provider == "hash":
        logger.warning("Using HashEmbeddingProvider for chat retrieval.")
        return HashEmbeddingProvider()
    return OpenAICompatibleEmbeddingProvider(cfg)
