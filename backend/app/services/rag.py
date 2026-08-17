from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from app.config import Settings, settings
from app.prompts import SYSTEM_PROMPT, build_user_prompt
from app.schemas.chat import ChatRequest, ChatResponse, Source
from app.services.embeddings import EmbeddingProvider, create_embedding_provider
from app.services.llm import LLMClient
from app.services.retriever import ChromaRetriever, RetrievedChunk

logger = logging.getLogger(__name__)


class RagServiceError(RuntimeError):
    """Raised when the RAG pipeline fails in a recoverable API sense."""


@dataclass
class RagDependencies:
    embedder: EmbeddingProvider
    retriever: ChromaRetriever
    llm: LLMClient


class RagService:
    def __init__(
        self,
        config: Settings | None = None,
        dependencies: RagDependencies | None = None,
    ) -> None:
        self.config = config or settings
        self._deps = dependencies

    @property
    def deps(self) -> RagDependencies:
        if self._deps is None:
            logger.info("RAG deps init: creating embedding provider")
            embedder = create_embedding_provider(self.config)
            logger.info("RAG deps init: connecting Chroma retriever path=%s", self.config.chroma_path)
            retriever = ChromaRetriever(embedder, self.config)
            logger.info(
                "RAG deps init: Chroma collection=%s count=%s",
                self.config.chroma_collection_name,
                retriever.count(),
            )
            logger.info("RAG deps init: creating LLM client")
            llm = LLMClient(self.config)
            self._deps = RagDependencies(
                embedder=embedder,
                retriever=retriever,
                llm=llm,
            )
            logger.info("RAG deps init: complete")
        return self._deps

    def _build_context(self, chunks: list[RetrievedChunk]) -> list[str]:
        blocks: list[str] = []
        total = 0
        for index, chunk in enumerate(chunks, start=1):
            block = (
                f"[Source {index}] title={chunk.title}\n"
                f"url={chunk.url}\n"
                f"section={chunk.section}\n"
                f"relevance={chunk.relevance:.3f}\n"
                f"content:\n{chunk.text}"
            )
            if total + len(block) > self.config.rag_max_context_chars and blocks:
                break
            blocks.append(block)
            total += len(block)
        return blocks

    def _to_sources(self, chunks: list[RetrievedChunk]) -> list[Source]:
        sources: list[Source] = []
        seen: set[tuple[str, str, str]] = set()
        for chunk in chunks:
            key = (chunk.title, chunk.url, chunk.section)
            if key in seen:
                continue
            seen.add(key)
            sources.append(
                Source(
                    title=chunk.title,
                    url=chunk.url,
                    section=chunk.section,
                    relevance=round(chunk.relevance, 4),
                )
            )
        return sources

    def chat(self, request: ChatRequest) -> ChatResponse:
        conversation_id = request.conversation_id or str(uuid.uuid4())
        logger.info(
            "RAG chat start conversationId=%s message_chars=%s",
            conversation_id,
            len(request.message),
        )

        try:
            logger.info("RAG stage=deps_and_retrieve conversationId=%s", conversation_id)
            chunks = self.deps.retriever.search(request.message)
        except Exception as exc:  # noqa: BLE001
            # Preserve the underlying cause in logs; keep a stable client-facing prefix.
            logger.exception(
                "Retrieval failed stage=embedding_or_chroma type=%s detail=%s",
                type(exc).__name__,
                exc,
            )
            raise RagServiceError(
                f"Failed to retrieve relevant BMI Hub content. ({type(exc).__name__}: {exc})"
            ) from exc

        if not chunks:
            answer = (
                "I could not find relevant information in the available BMI Hub content "
                "for that question."
            )
            chroma_count = None
            try:
                chroma_count = self.deps.retriever.count()
            except Exception:  # noqa: BLE001
                chroma_count = "unavailable"
            logger.warning(
                "RAG stage=empty_context conversationId=%s chroma_count=%s",
                conversation_id,
                chroma_count,
            )
            return ChatResponse(answer=answer, sources=[])

        context_blocks = self._build_context(chunks)
        logger.info(
            "RAG stage=context_built conversationId=%s chunks=%s context_blocks=%s",
            conversation_id,
            len(chunks),
            len(context_blocks),
        )
        user_prompt = build_user_prompt(question=request.message, context_blocks=context_blocks)

        try:
            logger.info("RAG stage=llm_complete conversationId=%s", conversation_id)
            answer = self.deps.llm.complete(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "LLM completion failed type=%s detail=%s",
                type(exc).__name__,
                exc,
            )
            raise RagServiceError(
                f"Failed to generate an answer from the language model. ({type(exc).__name__}: {exc})"
            ) from exc

        sources = self._to_sources(chunks)
        logger.info(
            "RAG chat complete conversationId=%s sources=%s answer_chars=%s",
            conversation_id,
            len(sources),
            len(answer),
        )
        return ChatResponse(answer=answer, sources=sources)


_rag_service: RagService | None = None


def get_rag_service() -> RagService:
    global _rag_service
    if _rag_service is None:
        _rag_service = RagService()
    return _rag_service


def reset_rag_service() -> None:
    global _rag_service
    _rag_service = None
