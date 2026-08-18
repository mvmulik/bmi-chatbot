"""Safe crawler logging — never emit cookies, tokens, or credentials."""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

logger = logging.getLogger("bmihub.crawler")

_SECRET_PATTERN = re.compile(
    r"(?i)(cookie|set-cookie|authorization|bearer|password|passwd|secret|token|mfa|otp)\s*[=:]\s*\S+"
)
_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+\S+")
_QUERY_PATTERN = re.compile(r"\?.*$")


def redact(message: str) -> str:
    text = _SECRET_PATTERN.sub(r"\1=***", str(message))
    text = _BEARER_PATTERN.sub("bearer ***", text)
    return text


def log_path(url: str) -> str:
    """Log only the path, never query strings that may carry session material."""
    parsed = urlparse(url or "")
    path = parsed.path or "/"
    return _QUERY_PATTERN.sub("", path)


def configure_crawler_logging(level: int = logging.INFO) -> None:
    if logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
