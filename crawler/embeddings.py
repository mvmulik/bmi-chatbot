"""Configurable embedding providers (Azure OpenAI / OpenAI-compatible)."""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Sequence

from dotenv import load_dotenv
from openai import AzureOpenAI, OpenAI

from crawler.config import ROOT_DIR

load_dotenv(ROOT_DIR / ".env")
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmbeddingSettings:
    api_type: str = "azure"
    api_key: str = ""
    api_base: str = ""
    api_version: str = "2024-08-01-preview"
    azure_deployment: str = ""
    openai_model: str = "text-embedding-3-small"
    batch_size: int = 64

    @classmethod
    def from_env(cls) -> EmbeddingSettings:
        return cls(
            api_type=os.getenv("OPENAI_API_TYPE", "azure").strip().lower() or "azure",
            api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            api_base=os.getenv("OPENAI_API_BASE", "").strip(),
            api_version=os.getenv("OPENAI_API_VERSION", "2024-08-01-preview").strip(),
            azure_deployment=os.getenv("OPENAI_EMBEDDING_DEPLOYMENT_NAME", "").strip(),
            openai_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small").strip()
            or "text-embedding-3-small",
            batch_size=int(os.getenv("EMBEDDING_BATCH_SIZE", "64")),
        )

    @property
    def model_name(self) -> str:
        if self.api_type == "azure":
            return self.azure_deployment or self.openai_model
        return self.openai_model


class EmbeddingProvider(ABC):
    """Interface for text embedding backends."""

    @abstractmethod
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        raise NotImplementedError

    @property
    @abstractmethod
    def model_name(self) -> str:
        raise NotImplementedError


class OpenAICompatibleEmbeddingProvider(EmbeddingProvider):
    """Azure OpenAI or OpenAI-compatible embeddings via the official SDK."""

    def __init__(self, settings: EmbeddingSettings | None = None) -> None:
        self.settings = settings or EmbeddingSettings.from_env()
        if not self.settings.api_key:
            raise ValueError("OPENAI_API_KEY is required for embeddings.")
        if self.settings.api_type == "azure":
            if not self.settings.api_base:
                raise ValueError("OPENAI_API_BASE is required for Azure embeddings.")
            if not self.settings.azure_deployment:
                raise ValueError(
                    "OPENAI_EMBEDDING_DEPLOYMENT_NAME is required for Azure embeddings."
                )
            self._client: AzureOpenAI | OpenAI = AzureOpenAI(
                api_key=self.settings.api_key,
                api_version=self.settings.api_version,
                azure_endpoint=self.settings.api_base,
            )
            self._model = self.settings.azure_deployment
        else:
            self._client = OpenAI(
                api_key=self.settings.api_key,
                base_url=self.settings.api_base or None,
            )
            self._model = self.settings.openai_model
        logger.info(
            "Embedding provider ready (type=%s, model=%s, batch_size=%s)",
            self.settings.api_type,
            self._model,
            self.settings.batch_size,
        )

    @property
    def model_name(self) -> str:
        return self._model

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []

        vectors: list[list[float]] = []
        batch_size = max(1, self.settings.batch_size)
        for start in range(0, len(texts), batch_size):
            batch = list(texts[start : start + batch_size])
            logger.debug("Embedding batch %s-%s (%s texts)", start, start + len(batch), len(batch))
            response = self._client.embeddings.create(model=self._model, input=batch)
            # Ensure order matches input.
            ordered = sorted(response.data, key=lambda item: item.index)
            vectors.extend([list(item.embedding) for item in ordered])
        return vectors


class HashEmbeddingProvider(EmbeddingProvider):
    """Deterministic local embeddings for offline tests (not for production retrieval quality)."""

    def __init__(self, dimensions: int = 32) -> None:
        self._dimensions = dimensions

    @property
    def model_name(self) -> str:
        return f"hash-embedding-{self._dimensions}"

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            values = [0.0] * self._dimensions
            for index, char in enumerate(text.encode("utf-8")):
                values[index % self._dimensions] += (char % 31) / 31.0
            norm = sum(v * v for v in values) ** 0.5 or 1.0
            vectors.append([v / norm for v in values])
        return vectors


def create_embedding_provider(
    settings: EmbeddingSettings | None = None,
    *,
    allow_hash_fallback: bool = False,
) -> EmbeddingProvider:
    """
    Create the configured embedding provider.

    Set EMBEDDING_PROVIDER=hash only for local tests/offline dry-runs.
    """
    provider_name = os.getenv("EMBEDDING_PROVIDER", "").strip().lower()
    cfg = settings or EmbeddingSettings.from_env()

    if provider_name == "hash" or (allow_hash_fallback and not cfg.api_key):
        logger.warning("Using HashEmbeddingProvider (not suitable for production RAG quality).")
        return HashEmbeddingProvider()

    return OpenAICompatibleEmbeddingProvider(cfg)
