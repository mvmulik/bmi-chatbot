"""Chunk metadata helpers for processed RAG documents."""

from __future__ import annotations

import hashlib
import re
from typing import Any


def slugify(value: str, *, fallback: str = "chunk") -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip().lower()).strip("-")
    return cleaned[:80] or fallback


def make_chunk_id(
    *,
    url: str,
    heading: str,
    index: int,
    text: str,
) -> str:
    digest = hashlib.sha1(f"{url}|{heading}|{index}|{text[:200]}".encode("utf-8")).hexdigest()[
        :12
    ]
    heading_slug = slugify(heading or "intro", fallback="intro")
    return f"{heading_slug}-{index:04d}-{digest}"


def build_chunk_metadata(
    *,
    chunk_id: str,
    page_title: str,
    url: str,
    section: str,
    heading: str,
    crawl_timestamp: str,
    source_type: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "chunk_id": chunk_id,
        "page_title": page_title,
        "url": url,
        "section": section,
        "heading": heading,
        "crawl_timestamp": crawl_timestamp,
        "source_type": source_type,
        "source": "BMI Hub",
    }
    if extra:
        metadata.update(extra)
    return metadata
