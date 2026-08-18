"""Query-time discover → scrape → index loop when retrieval is insufficient."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from app.config import Settings, settings
from app.services.retriever import RetrievedChunk

logger = logging.getLogger(__name__)

MAX_CRAWL_ITERATIONS = 5


class UrlDiscoverer(Protocol):
    def discover(self, question: str, *, limit: int = 5) -> list[str]:
        ...


class TargetedIngestor(Protocol):
    def ingest(self, urls: list[str]) -> int:
        """Scrape/process/index URLs. Return number of new/updated pages."""
        ...


@dataclass
class KnowledgeLoop:
    discoverer: UrlDiscoverer | None = None
    ingestor: TargetedIngestor | None = None
    max_iterations: int = MAX_CRAWL_ITERATIONS
    seen_urls: set[str] = field(default_factory=set)

    def context_is_sufficient(
        self,
        chunks: list[RetrievedChunk],
        *,
        min_relevance: float,
    ) -> bool:
        if not chunks:
            return False
        return any(chunk.relevance >= min_relevance for chunk in chunks)

    def fill_gaps(
        self,
        question: str,
        chunks: list[RetrievedChunk],
        *,
        retrieve: Callable[[str], list[RetrievedChunk]],
        min_relevance: float,
    ) -> list[RetrievedChunk]:
        current = chunks
        if self.context_is_sufficient(current, min_relevance=min_relevance):
            return current
        if self.discoverer is None:
            return current

        for iteration in range(1, self.max_iterations + 1):
            missing_urls = [
                url
                for url in self.discoverer.discover(question, limit=5)
                if url not in self.seen_urls
            ]
            if not missing_urls:
                logger.info("Knowledge loop stop: no new URLs iteration=%s", iteration)
                break
            self.seen_urls.update(missing_urls)
            ingested = 0
            if self.ingestor is not None:
                try:
                    ingested = self.ingestor.ingest(missing_urls)
                except Exception:
                    logger.exception("Targeted ingest failed iteration=%s", iteration)
                    break
            logger.info(
                "Knowledge loop iteration=%s urls=%s ingested=%s",
                iteration,
                missing_urls,
                ingested,
            )
            current = retrieve(question)
            if self.context_is_sufficient(current, min_relevance=min_relevance):
                return current
            if ingested == 0:
                break
        return current


class CatalogDiscoverer:
    def __init__(self, state_path: Path | None = None) -> None:
        self.state_path = state_path

    def discover(self, question: str, *, limit: int = 5) -> list[str]:
        try:
            from crawler.config import CrawlerSettings
            from crawler.state_store import CrawlStateStore
        except Exception as exc:  # noqa: BLE001
            logger.debug("Catalog discoverer unavailable: %s", exc)
            return []

        path = self.state_path or CrawlerSettings.from_env().state_path
        store = CrawlStateStore(path)
        records = store.search(question, limit=limit)
        urls = [record.url for record in records if record.url]
        if urls:
            return urls
        start = CrawlerSettings.from_env().start_url
        return [start] if start else []


class LiveCrawlIngestor:
    """Optional targeted crawl using the saved Playwright session."""

    def __init__(self, config: Settings | None = None) -> None:
        self.config = config or settings

    def ingest(self, urls: list[str]) -> int:
        if not urls:
            return 0
        try:
            from crawler.auth import storage_state_exists
            from crawler.config import CrawlerSettings
        except Exception as exc:  # noqa: BLE001
            logger.warning("Live crawl dependencies unavailable: %s", exc)
            return 0

        crawler_settings = CrawlerSettings.from_env()
        if not storage_state_exists(crawler_settings):
            logger.info("Live crawl skipped: no saved BMI Hub session")
            return 0

        max_pages = min(len(urls), max(1, getattr(self.config, "rag_live_crawl_max_pages", None) or self.config.rag_query_time_max_pages))
        try:
            from crawler.ingest import run_targeted_ingest

            result = run_targeted_ingest(
                seed_urls=urls[:max_pages],
                max_pages=max_pages,
                max_depth=1,
                mode="incremental",
                allow_interactive=False,
            )
        except Exception:
            logger.exception("Live crawl ingest failed")
            return 0
        return int(result.get("processed_pages") or 0)
