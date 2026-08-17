from __future__ import annotations

import logging

from fastapi import APIRouter

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
@router.get("/api/health")
def health_check() -> dict[str, str]:
    payload = {
        "status": "healthy",
        "app": settings.app_name,
        "environment": settings.app_env,
    }
    logger.debug("Health check ok")
    return payload
