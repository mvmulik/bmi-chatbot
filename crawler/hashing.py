"""Content hashing for crawl duplicate detection."""

from __future__ import annotations

import hashlib
import re


def normalize_for_hash(text: str) -> str:
    """Collapse whitespace so cosmetic HTML changes do not force a reindex."""
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


def generate_content_hash(text: str) -> str:
    payload = normalize_for_hash(text).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
