from __future__ import annotations

import logging
import re
from typing import Any

import chromadb
from fastapi import APIRouter, Query

from app.config import settings
from app.services.embeddings import create_embedding_provider
from app.services.retriever import ChromaRetriever

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/debug", tags=["debug"])


def _configured(value: str | None) -> bool:
    """True only if value is present and not an unfilled placeholder."""
    if not value or not str(value).strip():
        return False
    return "REPLACE_WITH" not in str(value).upper()


def _safe_error(exc: BaseException) -> str:
    """Return a short exception summary without secrets."""
    text = str(exc).strip() or type(exc).__name__
    text = re.sub(r"(?i)(api[_-]?key|password|secret|token)\s*[=:]\s*\S+", r"\1=***", text)
    text = re.sub(r"(?i)\bbearer\s+\S+", "bearer ***", text)
    text = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}", "***", text)
    return f"{type(exc).__name__}: {text}"


@router.get("/rag")
def debug_rag() -> dict[str, Any]:
    """Safe RAG pipeline diagnostics (no secrets)."""
    chroma_path = settings.chroma_path
    collection_name = settings.chroma_collection_name
    collection_exists = False
    document_count = 0
    chroma_error: str | None = None
    collections: list[str] = []

    embedding_configured = _configured(settings.embedding_api_key) and (
        settings.openai_api_type.lower() != "azure"
        or (
            _configured(settings.embedding_api_base)
            and _configured(settings.embedding_model)
        )
    )
    if (settings.embedding_provider or "").strip().lower() == "hash":
        embedding_configured = True

    llm_configured = _configured(settings.openai_api_key) and (
        settings.openai_api_type.lower() != "azure"
        or (
            _configured(settings.openai_api_base)
            and _configured(settings.chat_model)
        )
    )

    embedding_probe: dict[str, Any] = {
        "ok": False,
        "dimensions": None,
        "error": None,
    }
    failure_point: str | None = None

    try:
        client = chromadb.PersistentClient(path=str(chroma_path))
        collections = [item.name for item in client.list_collections()]
        collection_exists = collection_name in collections
        if collection_exists:
            document_count = client.get_collection(collection_name).count()
        else:
            # Match runtime retriever behavior (get_or_create) for count reporting.
            document_count = client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
            ).count()
            collection_exists = True
            collections = [item.name for item in client.list_collections()]
    except Exception as exc:  # noqa: BLE001
        chroma_error = _safe_error(exc)
        failure_point = "chroma"
        logger.exception("debug/rag chroma inspection failed")

    if embedding_configured:
        try:
            embedder = create_embedding_provider(settings)
            vector = embedder.embed_query("debug rag probe")
            embedding_probe = {
                "ok": True,
                "dimensions": len(vector),
                "error": None,
            }
        except Exception as exc:  # noqa: BLE001
            embedding_probe = {
                "ok": False,
                "dimensions": None,
                "error": _safe_error(exc),
            }
            failure_point = failure_point or "embedding"
            logger.exception("debug/rag embedding probe failed")
    else:
        failure_point = failure_point or "embedding_config"
        embedding_probe["error"] = (
            "OPENAI_EMBEDDING_API_KEY or OPENAI_API_KEY is not configured."
        )

    if document_count == 0 and failure_point is None:
        failure_point = "empty_index"

    if not llm_configured and failure_point is None:
        failure_point = "llm_config"

    healthy = (
        chroma_error is None
        and collection_exists
        and document_count > 0
        and embedding_configured
        and embedding_probe["ok"]
        and llm_configured
    )

    payload = {
        "status": "healthy" if healthy else "unhealthy",
        "chroma_path": str(chroma_path),
        "chroma_path_exists": chroma_path.exists(),
        "collection_exists": collection_exists,
        "collection_name": collection_name,
        "collections": collections,
        "document_count": document_count,
        "embedding_configured": embedding_configured,
        "embedding_provider": (settings.embedding_provider or "openai_compatible"),
        "embedding_model": settings.embedding_model,
        "embedding_probe": embedding_probe,
        "llm_configured": llm_configured,
        "llm_model": settings.chat_model,
        "openai_api_type": settings.openai_api_type,
        "failure_point": failure_point,
        "chroma_error": chroma_error,
        "notes": [
            "Secrets are never returned by this endpoint.",
            "document_count==0 means crawl/process/index has not populated Chroma.",
        ],
    }
    logger.info(
        "debug/rag status=%s docs=%s embed_ok=%s llm_configured=%s failure_point=%s",
        payload["status"],
        document_count,
        embedding_probe["ok"],
        llm_configured,
        failure_point,
    )
    return payload


@router.get("/search")
def debug_search(q: str = Query(..., min_length=1, max_length=2000)) -> dict[str, Any]:
    """Run Chroma similarity search only (no LLM)."""
    logger.info("debug/search q_chars=%s", len(q))
    try:
        embedder = create_embedding_provider(settings)
        retriever = ChromaRetriever(embedder, settings)
        count = retriever.count()
        if count == 0:
            return {
                "query": q,
                "document_count": 0,
                "result_count": 0,
                "results": [],
                "error": "Chroma collection is empty; nothing to search.",
            }

        # Access collection directly to include raw distances in the response.
        collection = retriever._collection()  # noqa: SLF001
        query_embedding = embedder.embed_query(q)
        raw = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(settings.rag_top_k, count),
            include=["documents", "metadatas", "distances"],
        )
        documents = (raw.get("documents") or [[]])[0]
        metadatas = (raw.get("metadatas") or [[]])[0]
        distances = (raw.get("distances") or [[]])[0]
        ids = (raw.get("ids") or [[]])[0]

        results: list[dict[str, Any]] = []
        for index, doc in enumerate(documents):
            metadata = metadatas[index] if index < len(metadatas) else {}
            metadata = metadata or {}
            distance = distances[index] if index < len(distances) else None
            relevance = None
            if distance is not None:
                relevance = max(0.0, min(1.0, 1.0 - float(distance)))
            results.append(
                {
                    "id": ids[index] if index < len(ids) else None,
                    "title": metadata.get("page_title")
                    or metadata.get("title")
                    or "BMI Hub",
                    "url": metadata.get("url") or "",
                    "section": metadata.get("section") or metadata.get("heading") or "",
                    "distance": distance,
                    "relevance": relevance,
                    "preview": (doc or "")[:240],
                }
            )

        return {
            "query": q,
            "document_count": count,
            "result_count": len(results),
            "results": results,
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("debug/search failed")
        return {
            "query": q,
            "document_count": None,
            "result_count": 0,
            "results": [],
            "error": _safe_error(exc),
        }
