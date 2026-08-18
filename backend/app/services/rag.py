from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from app.config import Settings, settings
from app.constants import INSUFFICIENT_ANSWER
from app.prompts import SYSTEM_PROMPT, build_user_prompt
from app.schemas.chat import ChatRequest, ChatResponse, Source
from app.services.conversation import ConversationStore, get_conversation_store
from app.services.embeddings import EmbeddingProvider, create_embedding_provider
from app.services.knowledge import (
    CatalogDiscoverer,
    KnowledgeLoop,
    LiveCrawlIngestor,
)
from app.services.llm import LLMClient
from app.services.retriever import ChromaRetriever, RetrievedChunk, context_is_sufficient

logger = logging.getLogger(__name__)


class RagServiceError(RuntimeError):
    """Raised when the RAG pipeline fails in a recoverable API sense."""


@dataclass
class RagDependencies:
    embedder: EmbeddingProvider
    retriever: ChromaRetriever
    llm: LLMClient
    conversations: ConversationStore | None = None
    knowledge_loop: KnowledgeLoop | None = None


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
            loop = KnowledgeLoop(
                discoverer=CatalogDiscoverer(),
                ingestor=LiveCrawlIngestor(self.config) if self.config.rag_query_time_crawl else None,
                max_iterations=self.config.rag_max_iterations,
            )
            self._deps = RagDependencies(
                embedder=embedder,
                retriever=retriever,
                llm=llm,
                conversations=get_conversation_store(),
                knowledge_loop=loop,
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
                    relevance=round(min(1.0, max(0.0, chunk.relevance)), 4),
                )
            )
        return sources

    def _history_text(self, conversation_id: str) -> str:
        store = self.deps.conversations
        if store is None:
            return ""
        turns = store.get(conversation_id)
        if not turns:
            return ""
        latest = turns[-1]
        return f"Previous question: {latest.question}\nPrevious answer: {latest.answer[:500]}"

    def _insufficient(self) -> ChatResponse:
        return ChatResponse(answer=INSUFFICIENT_ANSWER, sources=[])

    def chat(self, request: ChatRequest) -> ChatResponse:
        conversation_id = request.conversation_id or str(uuid.uuid4())
        logger.info(
            "RAG chat start conversationId=%s message_chars=%s",
            conversation_id,
            len(request.message),
        )
        store = self.deps.conversations
        query = request.message
        if store is not None:
            query = store.expand_query(conversation_id, request.message)

        try:
            logger.info("RAG stage=deps_and_retrieve conversationId=%s", conversation_id)
            chunks = self.deps.retriever.search(query)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Retrieval failed stage=embedding_or_chroma type=%s detail=%s",
                type(exc).__name__,
                exc,
            )
            raise RagServiceError(
                f"Failed to retrieve relevant BMI Hub content. ({type(exc).__name__}: {exc})"
            ) from exc

        loop = self.deps.knowledge_loop
        if loop is not None and not context_is_sufficient(
            chunks,
            query,
            min_relevance=self.config.rag_min_relevance,
        ):
            chunks = loop.fill_gaps(
                query,
                chunks,
                retrieve=self.deps.retriever.search,
                min_relevance=self.config.rag_min_relevance,
            )

        if not context_is_sufficient(
            chunks,
            query,
            min_relevance=self.config.rag_min_relevance,
        ):
            logger.warning(
                "RAG stage=insufficient_context conversationId=%s chunks=%s",
                conversation_id,
                len(chunks),
            )
            if store is not None:
                store.add(conversation_id, request.message, INSUFFICIENT_ANSWER)
            return self._insufficient()

        context_blocks = self._build_context(chunks)
        logger.info(
            "RAG stage=context_built conversationId=%s chunks=%s context_blocks=%s",
            conversation_id,
            len(chunks),
            len(context_blocks),
        )
        user_prompt = build_user_prompt(
            question=request.message,
            context_blocks=context_blocks,
            conversation_context=self._history_text(conversation_id),
        )

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
        if store is not None:
            store.add(conversation_id, request.message, answer)
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
