from __future__ import annotations

import logging
from logging.config import dictConfig

from app.config import settings


def configure_logging() -> None:
    level = settings.log_level.upper()
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                    "datefmt": "%Y-%m-%d %H:%M:%S",
                }
            },
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                }
            },
            "root": {
                "level": level,
                "handlers": ["default"],
            },
            "loggers": {
                "uvicorn": {"level": level},
                "uvicorn.error": {"level": level},
                "uvicorn.access": {"level": level},
                "app": {"level": level, "propagate": True},
            },
        }
    )
    logging.getLogger(__name__).debug("Logging configured at %s", level)
