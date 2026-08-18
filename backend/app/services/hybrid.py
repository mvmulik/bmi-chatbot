"""Hybrid vector + keyword ranking helpers."""

from __future__ import annotations

import re
from collections import defaultdict

STOPWORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "of",
    "for",
    "to",
    "in",
    "on",
    "at",
    "is",
    "are",
    "was",
    "were",
    "be",
    "can",
    "i",
    "my",
    "me",
    "we",
    "our",
    "you",
    "your",
    "what",
    "which",
    "who",
    "how",
    "where",
    "when",
    "why",
    "do",
    "does",
    "did",
    "please",
    "tell",
    "about",
    "from",
    "with",
    "this",
    "that",
    "it",
    "bmi",
    "hub",
}


def extract_keywords(query: str, *, limit: int = 8) -> list[str]:
    tokens = re.findall(r"[a-zA-Z0-9][a-zA-Z0-9-]{2,}", query.lower())
    seen: set[str] = set()
    keywords: list[str] = []
    for token in tokens:
        if token in STOPWORDS or token in seen:
            continue
        seen.add(token)
        keywords.append(token)
        if len(keywords) >= limit:
            break
    return keywords


def reciprocal_rank_fusion(
    ranked_id_lists: list[list[str]],
    *,
    k: int = 60,
) -> dict[str, float]:
    scores: dict[str, float] = defaultdict(float)
    for ranked in ranked_id_lists:
        for rank, item_id in enumerate(ranked, start=1):
            scores[item_id] += 1.0 / (k + rank)
    return dict(scores)
