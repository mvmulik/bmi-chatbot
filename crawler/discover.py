"""Query-oriented URL discovery helpers constrained to the BMI Hub domain."""

from __future__ import annotations

import re
from typing import Iterable
from urllib.parse import urlparse

from crawler.extractor import is_internal_url, normalize_url
from crawler.state_store import CrawlRecord

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
    "whom",
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
}

DOCUMENT_EXTENSIONS = (
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
)


def extract_query_terms(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9][a-z0-9-]{2,}", (text or "").lower())
    seen: set[str] = set()
    terms: list[str] = []
    for token in tokens:
        if token in STOPWORDS or token in seen:
            continue
        seen.add(token)
        terms.append(token)
    return terms


def is_document_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return path.endswith(DOCUMENT_EXTENSIONS)


def score_text(text: str, terms: Iterable[str]) -> int:
    blob = (text or "").lower()
    return sum(1 for term in terms if term in blob)


def rank_records_for_query(
    records: Iterable[CrawlRecord],
    question: str,
    *,
    limit: int = 10,
) -> list[str]:
    terms = extract_query_terms(question)
    ranked: list[tuple[int, str]] = []
    for record in records:
        url = normalize_url(record.url) or record.url
        if not url or not is_internal_url(url):
            continue
        haystack = f"{record.title} {url} {' '.join(record.document_links or [])}"
        score = score_text(haystack, terms)
        if score:
            ranked.append((score, url))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [url for _score, url in ranked[:limit]]


def rank_urls_for_query(urls: Iterable[str], question: str, *, limit: int = 10) -> list[str]:
    terms = extract_query_terms(question)
    ranked: list[tuple[int, str]] = []
    seen: set[str] = set()
    for raw in urls:
        url = normalize_url(raw) or raw
        if not url or url in seen or not is_internal_url(url):
            continue
        seen.add(url)
        score = score_text(url, terms)
        if score:
            ranked.append((score, url))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [url for _score, url in ranked[:limit]]
