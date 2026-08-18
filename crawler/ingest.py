"""Crawl → process → incremental index pipeline used by admin and query-time refresh."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from crawler.config import CrawlerSettings, ROOT_DIR
from crawler.crawler import BmiHubCrawler
from crawler.indexer import VectorIndexer
from processor.config import ProcessorSettings
from processor.pipeline import ContentProcessor


def _run_async(coro):  # noqa: ANN001
    """Run an async coroutine from sync code, including inside FastAPI's event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    outcome: dict[str, Any] = {}

    def _runner() -> None:
        try:
            outcome["value"] = asyncio.run(coro)
        except Exception as exc:  # noqa: BLE001
            outcome["error"] = exc

    import threading

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()
    if "error" in outcome:
        raise outcome["error"]
    if "value" not in outcome:
        raise RuntimeError("Timed crawl task failed to return a result.")
    return outcome["value"]


def process_and_index(crawl_dir: Path) -> dict[str, Any]:
    pages_dir = crawl_dir / "pages"
    if not pages_dir.is_dir() or not any(pages_dir.glob("*.json")):
        return {"processed_pages": 0, "chunks": 0, "upserted": 0, "process_dir": ""}

    processor = ContentProcessor(ProcessorSettings.from_env())
    process_result = processor.run(crawl_dir=crawl_dir)
    indexer = VectorIndexer()
    index_stats = indexer.incremental_index(process_dir=process_result.run_dir)
    return {
        "processed_pages": process_result.stats.processed_pages,
        "chunks": process_result.stats.total_chunks,
        "upserted": index_stats.upserted,
        "process_dir": str(process_result.run_dir),
        "index": asdict(index_stats),
    }


def run_targeted_ingest(
    *,
    seed_urls: list[str],
    max_pages: int = 5,
    max_depth: int = 1,
    mode: str = "incremental",
    allow_interactive: bool = False,
) -> dict[str, Any]:
    settings = replace(
        CrawlerSettings.from_env(),
        start_url=(seed_urls[0] if seed_urls else CrawlerSettings.from_env().start_url),
        max_pages=max_pages,
        max_depth=max_depth,
        headless=True,
        crawl_mode=mode,
    )
    crawler = BmiHubCrawler(
        settings,
        mode=mode,
        seed_urls=seed_urls,
        allow_interactive=allow_interactive,
    )
    report_path: Path = _run_async(crawler.run())
    ingest = process_and_index(report_path.parent)
    return {
        "crawl_report": str(report_path),
        "successful_urls": crawler.state.successful,
        "failed_urls": crawler.state.failed,
        **ingest,
    }


def run_admin_crawl(mode: str, *, max_pages: int | None = None) -> dict[str, Any]:
    settings = CrawlerSettings.from_env()
    if max_pages is not None:
        settings = replace(settings, max_pages=max_pages, crawl_mode=mode)
    else:
        settings = replace(settings, crawl_mode=mode)
    crawler = BmiHubCrawler(settings, mode=mode, allow_interactive=True)
    report_path: Path = _run_async(crawler.run())
    processor = ContentProcessor(ProcessorSettings.from_env())
    process_result = processor.run(crawl_dir=report_path.parent)
    indexer = VectorIndexer()
    if mode == "full":
        index_stats = indexer.full_rebuild(process_dir=process_result.run_dir)
    else:
        index_stats = indexer.incremental_index(process_dir=process_result.run_dir)
    return {
        "mode": mode,
        "crawl_report": str(report_path),
        "totals": {
            "total_urls_discovered": crawler.state.stats.total_pages_discovered,
            "total_urls_processed": crawler.state.stats.successfully_crawled_pages,
            "new_pages": crawler.state.stats.new_pages,
            "updated_pages": crawler.state.stats.updated_pages,
            "skipped_pages": crawler.state.stats.skipped_pages,
            "failed_pages": crawler.state.stats.failed_pages,
            "documents_indexed": index_stats.upserted,
            "chunks_created": process_result.stats.total_chunks,
        },
        "process_dir": str(process_result.run_dir),
        "project_root": str(ROOT_DIR),
    }
