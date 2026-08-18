"""Persistent crawl-state database for incremental BMI Hub crawls."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

STATUS_PENDING = "PENDING"
STATUS_PROCESSING = "PROCESSING"
STATUS_PROCESSED = "PROCESSED"
STATUS_UPDATED = "UPDATED"
STATUS_FAILED = "FAILED"
STATUS_ACCESS_DENIED = "ACCESS_DENIED"
STATUS_SKIPPED = "SKIPPED"

VALID_STATUSES = {
    STATUS_PENDING,
    STATUS_PROCESSING,
    STATUS_PROCESSED,
    STATUS_UPDATED,
    STATUS_FAILED,
    STATUS_ACCESS_DENIED,
    STATUS_SKIPPED,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class CrawlRecord:
    url: str
    title: str = ""
    content_hash: str = ""
    last_scraped: str = ""
    last_updated: str = ""
    status: str = STATUS_PENDING
    error: str = ""
    document_links: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["document_links"] = list(self.document_links or [])
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> CrawlRecord:
        return cls(
            url=str(payload.get("url") or ""),
            title=str(payload.get("title") or ""),
            content_hash=str(payload.get("content_hash") or ""),
            last_scraped=str(payload.get("last_scraped") or ""),
            last_updated=str(payload.get("last_updated") or ""),
            status=str(payload.get("status") or STATUS_PENDING),
            error=str(payload.get("error") or ""),
            document_links=list(payload.get("document_links") or []),
        )


class CrawlStateStore:
    """JSON-backed URL state used to skip unchanged pages and retry failures."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.records: dict[str, CrawlRecord] = {}
        self.load()

    def load(self) -> None:
        if not self.path.is_file():
            self.records = {}
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            self.records = {}
            return
        urls = payload.get("urls", payload) if isinstance(payload, dict) else {}
        self.records = {}
        if isinstance(urls, dict):
            for url, raw in urls.items():
                if isinstance(raw, dict):
                    record = CrawlRecord.from_dict({"url": url, **raw})
                    if record.url:
                        self.records[record.url] = record

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": _utc_now(),
            "urls": {url: record.to_dict() for url, record in sorted(self.records.items())},
        }
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def get(self, url: str) -> CrawlRecord | None:
        return self.records.get(url)

    def upsert(self, url: str, **changes: Any) -> CrawlRecord:
        record = self.records.get(url) or CrawlRecord(url=url)
        for key, value in changes.items():
            if hasattr(record, key) and value is not None:
                setattr(record, key, value)
        if "last_updated" not in changes:
            record.last_updated = _utc_now()
        self.records[url] = record
        return record

    def should_skip_unchanged(self, url: str, content_hash: str) -> bool:
        record = self.get(url)
        return bool(record and record.content_hash and record.content_hash == content_hash)

    def search(self, question: str, *, limit: int = 10) -> list[CrawlRecord]:
        from crawler.discover import rank_records_for_query

        urls = rank_records_for_query(self.records.values(), question, limit=limit)
        found = [self.records[url] for url in urls if url in self.records]
        if found:
            return found
        return [
            record
            for record in self.records.values()
            if record.status in {STATUS_PENDING, STATUS_FAILED}
        ][:limit]

    def failed_or_pending_urls(self) -> list[str]:
        return [
            record.url
            for record in self.records.values()
            if record.status in {STATUS_FAILED, STATUS_PENDING, STATUS_PROCESSING}
        ]

    def processed_urls(self) -> set[str]:
        return {
            record.url
            for record in self.records.values()
            if record.status in {STATUS_PROCESSED, STATUS_UPDATED}
        }

    def all_records(self) -> Iterable[CrawlRecord]:
        return self.records.values()
