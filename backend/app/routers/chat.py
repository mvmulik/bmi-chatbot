from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from app.schemas.chat import ChatRequest, ChatResponse
from app.services.rag import RagService, RagServiceError, get_rag_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    request: Request,
    rag_service: RagService = Depends(get_rag_service),
) -> ChatResponse:
    logger.info(
        "POST /api/chat from=%s conversationId=%s",
        request.client.host if request.client else "unknown",
        payload.conversation_id,
    )
    try:
        return rag_service.chat(payload)
    except RagServiceError as exc:
        logger.error("RAG service error: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected chat failure")
        raise HTTPException(
            status_code=500,
            detail="Unexpected error while processing the chat request.",
        ) from exc
