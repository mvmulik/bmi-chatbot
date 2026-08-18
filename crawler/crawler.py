"""BMI Hub authenticated website crawler."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
from collections import deque
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from crawler.auth import (
    AuthenticationError,
    create_authenticated_context,
    probe_authenticated_session,
    refresh_storage_state,
    storage_state_exists,
)
from crawler.config import CrawlerSettings
from crawler.discover import is_document_url
from crawler.extractor import (
    extract_page_content,
    is_internal_url,
    is_probably_html_url,
    normalize_url,
    utc_now_iso,
)
from crawler.hashing import generate_content_hash
from crawler.robots import RobotsPolicy
from crawler.state_store import (
    STATUS_ACCESS_DENIED,
    STATUS_FAILED,
    STATUS_PROCESSED,
    STATUS_SKIPPED,
    STATUS_UPDATED,
    CrawlStateStore,
)


@dataclass
class CrawlStats:
    total_pages_discovered: int = 0
    successfully_crawled_pages: int = 0
    failed_pages: int = 0
    skipped_pages: int = 0
    external_links: int = 0
    duplicate_links: int = 0
    robots_blocked: int = 0
    non_html_skipped: int = 0
    max_depth_reached: int = 0
    new_pages: int = 0
    updated_pages: int = 0
    unchanged_pages: int = 0
    access_denied_pages: int = 0
    document_links: int = 0


@dataclass
class CrawlState:
    queue: deque[tuple[str, int]] = field(default_factory=deque)
    queued: set[str] = field(default_factory=set)
    visited: set[str] = field(default_factory=set)
    successful: list[str] = field(default_factory=list)
    failed: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    external_links: set[str] = field(default_factory=set)
    duplicates: set[str] = field(default_factory=set)
    document_links: set[str] = field(default_factory=set)
    stats: CrawlStats = field(default_factory=CrawlStats)


def _slug_for_url(url: str) -> str:
    parsed = urlparse(url)
    raw = f"{parsed.netloc}{parsed.path}"
    if parsed.query:
        raw += f"?{parsed.query}"
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", raw).strip("_")
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    if not cleaned:
        cleaned = "root"
    return f"{cleaned[:120]}_{digest}"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _looks_like_access_denied(status: int | None, page_url: str, title: str, html: str) -> bool:
    if status in {401, 403}:
        return True
    haystack = f"{page_url} {title} {html[:2000]}".lower()
    markers = ("access denied", "401 unauthorized", "403 forbidden", "you don't have access")
    return any(marker in haystack for marker in markers)


class BmiHubCrawler:
    def __init__(
        self,
        settings: CrawlerSettings,
        *,
        force_reauth: bool = False,
        mode: str | None = None,
        seed_urls: list[str] | None = None,
        allow_interactive: bool = True,
    ) -> None:
        self.settings = settings
        self.force_reauth = force_reauth
        self.mode = (mode or settings.crawl_mode or "incremental").strip().lower()
        if self.mode not in {"full", "incremental"}:
            raise ValueError("crawl mode must be 'full' or 'incremental'")
        self.seed_urls = seed_urls or []
        self.allow_interactive = allow_interactive
        self.robots = RobotsPolicy(settings)
        self.state = CrawlState()
        self.store = CrawlStateStore(settings.state_path)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.run_dir = settings.output_dir / f"crawl_{stamp}"
        self.pages_dir = self.run_dir / "pages"

    def _enqueue(self, url: str, depth: int, *, source: str) -> None:
        normalized = normalize_url(url)
        if not normalized:
            return

        if not is_internal_url(normalized):
            if normalized not in self.state.external_links:
                self.state.external_links.add(normalized)
                self.state.stats.external_links += 1
            return

        if is_document_url(normalized):
            if normalized not in self.state.document_links:
                self.state.document_links.add(normalized)
                self.state.stats.document_links += 1
                self.store.upsert(
                    normalized,
                    status=STATUS_SKIPPED,
                    error="linked_document",
                    title="",
                )
            self.state.skipped.append(
                {"url": normalized, "reason": "document_link", "source": source}
            )
            self.state.stats.skipped_pages += 1
            return

        if not is_probably_html_url(normalized):
            self.state.skipped.append(
                {"url": normalized, "reason": "non_html_asset", "source": source}
            )
            self.state.stats.skipped_pages += 1
            self.state.stats.non_html_skipped += 1
            return

        if not self.robots.allows(normalized):
            self.state.skipped.append(
                {"url": normalized, "reason": "robots_disallowed", "source": source}
            )
            self.state.stats.skipped_pages += 1
            self.state.stats.robots_blocked += 1
            return

        if depth > self.settings.max_depth:
            self.state.skipped.append(
                {"url": normalized, "reason": "max_depth_exceeded", "source": source}
            )
            self.state.stats.skipped_pages += 1
            self.state.stats.max_depth_reached += 1
            return

        if normalized in self.state.queued or normalized in self.state.visited:
            self.state.duplicates.add(normalized)
            self.state.stats.duplicate_links += 1
            return

        if len(self.state.successful) + len(self.state.queue) >= self.settings.max_pages:
            self.state.skipped.append(
                {"url": normalized, "reason": "max_pages_budget", "source": source}
            )
            self.state.stats.skipped_pages += 1
            return

        self.state.queue.append((normalized, depth))
        self.state.queued.add(normalized)
        self.state.stats.total_pages_discovered += 1
        if self.store.get(normalized) is None:
            self.store.upsert(normalized, status="PENDING")

    def _seed_queue(self) -> None:
        seeds = [normalize_url(url) for url in self.seed_urls]
        seeds = [url for url in seeds if url]
        start = normalize_url(self.settings.start_url)
        if start and start not in seeds:
            seeds.insert(0, start)
        if not seeds:
            raise ValueError(f"Invalid start URL: {self.settings.start_url}")

        for url in seeds:
            self._enqueue(url, 0, source="seed")

        if self.mode == "incremental":
            for url in self.store.failed_or_pending_urls():
                self._enqueue(url, 0, source="retry_state")

    async def run(self) -> Path:
        self.settings.output_dir.mkdir(parents=True, exist_ok=True)
        self.pages_dir.mkdir(parents=True, exist_ok=True)
        self.robots.load()
        self._seed_queue()

        if not self.allow_interactive and not storage_state_exists(self.settings):
            raise AuthenticationError(
                "No saved BMI Hub session is available. Run an interactive crawl first."
            )

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=self.settings.headless)
            try:
                context = await create_authenticated_context(
                    browser,
                    self.settings,
                    force_reauth=self.force_reauth if self.allow_interactive else False,
                )
                page = await context.new_page()
                page.set_default_timeout(self.settings.navigation_timeout_ms)

                if not await probe_authenticated_session(page, self.settings):
                    if not self.allow_interactive:
                        raise AuthenticationError(
                            "Saved BMI Hub session is invalid and interactive login is disabled."
                        )
                    print(
                        "Saved session appears invalid. Starting interactive login…",
                        file=sys.stderr,
                    )
                    await context.close()
                    context = await create_authenticated_context(
                        browser,
                        self.settings,
                        force_reauth=True,
                    )
                    page = await context.new_page()
                    page.set_default_timeout(self.settings.navigation_timeout_ms)

                while self.state.queue and len(self.state.successful) < self.settings.max_pages:
                    url, depth = self.state.queue.popleft()
                    if url in self.state.visited:
                        self.state.stats.duplicate_links += 1
                        continue

                    self.state.visited.add(url)
                    await self._crawl_one(page, url, depth)
                    await asyncio.sleep(self.settings.request_delay_seconds)

                await refresh_storage_state(context, self.settings)
                await context.close()
            finally:
                await browser.close()

        self.store.save()
        report_path = self._write_report()
        print(f"Crawl complete. Report: {report_path}")
        return report_path

    async def _goto_with_retries(self, page: Any, url: str) -> tuple[Any, int | None]:
        last_error: Exception | None = None
        attempts = max(1, self.settings.max_retries)
        for attempt in range(1, attempts + 1):
            try:
                response = await page.goto(url, wait_until="domcontentloaded")
                status = response.status if response else None
                return response, status
            except (PlaywrightTimeoutError, PlaywrightError) as exc:
                last_error = exc
                if attempt >= attempts:
                    raise
                await asyncio.sleep(min(2 * attempt, 6))
        raise last_error or PlaywrightError(f"Failed to open {url}")

    async def _crawl_one(self, page: Any, url: str, depth: int) -> None:
        print(f"[{len(self.state.successful) + 1}/{self.settings.max_pages}] depth={depth} {url}")
        previous = self.store.get(url)
        self.store.upsert(url, status="PROCESSING")
        try:
            _response, status = await self._goto_with_retries(page, url)
            final_url = normalize_url(page.url) or page.url

            if status is not None and status >= 400:
                access_denied = status in {401, 403}
                self._record_failure(
                    url,
                    final_url=final_url,
                    error_type="ACCESS_DENIED" if access_denied else "http_error",
                    status_code=status,
                    message=f"HTTP {status}",
                )
                return

            html = await page.content()
            extracted = extract_page_content(
                url=url,
                final_url=final_url,
                html=html,
                status_code=status,
            )
            title = str(extracted.get("page_title") or "")
            if _looks_like_access_denied(status, final_url, title, html):
                self._record_failure(
                    url,
                    final_url=final_url,
                    error_type="ACCESS_DENIED",
                    status_code=status,
                    message="Access denied or login page detected",
                )
                return

            extracted["depth"] = depth
            content_hash = str(extracted.get("content_hash") or generate_content_hash(html))
            unchanged = (
                self.mode == "incremental"
                and previous is not None
                and bool(previous.content_hash)
                and previous.content_hash == content_hash
            )

            if unchanged:
                self.state.skipped.append({"url": url, "reason": "unchanged_content"})
                self.state.stats.skipped_pages += 1
                self.state.stats.unchanged_pages += 1
                self.store.upsert(
                    url,
                    title=title,
                    content_hash=content_hash,
                    last_scraped=utc_now_iso(),
                    status=STATUS_SKIPPED,
                    error="",
                )
            else:
                out_path = self.pages_dir / f"{_slug_for_url(url)}.json"
                _write_json(out_path, extracted)
                self.state.successful.append(url)
                self.state.stats.successfully_crawled_pages += 1
                is_new = previous is None or not previous.content_hash
                status_name = STATUS_PROCESSED if is_new else STATUS_UPDATED
                if is_new:
                    self.state.stats.new_pages += 1
                else:
                    self.state.stats.updated_pages += 1
                self.store.upsert(
                    url,
                    title=title,
                    content_hash=content_hash,
                    last_scraped=utc_now_iso(),
                    last_updated=utc_now_iso(),
                    status=status_name,
                    error="",
                    document_links=[
                        link.get("url", "")
                        for link in extracted.get("links", [])
                        if is_document_url(str(link.get("url", "")))
                    ],
                )

            for link in extracted.get("links", []):
                link_url = link.get("url", "")
                self._enqueue(link_url, depth + 1, source=url)

        except (PlaywrightTimeoutError, PlaywrightError) as exc:
            self._record_failure(
                url,
                error_type="playwright_error",
                message=str(exc),
            )
        except Exception as exc:  # noqa: BLE001 - record unexpected page failures
            self._record_failure(
                url,
                error_type="unexpected_error",
                message=str(exc),
            )

    def _record_failure(
        self,
        url: str,
        *,
        final_url: str = "",
        error_type: str,
        message: str,
        status_code: int | None = None,
    ) -> None:
        access_denied = error_type == "ACCESS_DENIED"
        record = {
            "url": url,
            "final_url": final_url,
            "error_type": error_type,
            "status_code": status_code,
            "message": message,
            "timestamp": utc_now_iso(),
        }
        self.state.failed.append(record)
        self.state.stats.failed_pages += 1
        if access_denied:
            self.state.stats.access_denied_pages += 1
        self.store.upsert(
            url,
            status=STATUS_ACCESS_DENIED if access_denied else STATUS_FAILED,
            error=message,
            last_scraped=utc_now_iso(),
        )

    def _write_report(self) -> Path:
        stats = self.state.stats
        report = {
            "started_from": self.settings.start_url,
            "mode": self.mode,
            "run_directory": str(self.run_dir),
            "generated_at": utc_now_iso(),
            "settings": {
                "max_pages": self.settings.max_pages,
                "max_depth": self.settings.max_depth,
                "request_delay_seconds": self.settings.request_delay_seconds,
                "respect_robots": self.settings.respect_robots,
                "headless": self.settings.headless,
                "max_retries": self.settings.max_retries,
            },
            "totals": {
                "total_urls_discovered": stats.total_pages_discovered,
                "total_urls_processed": stats.successfully_crawled_pages,
                "new_pages": stats.new_pages,
                "updated_pages": stats.updated_pages,
                "skipped_pages": stats.skipped_pages,
                "unchanged_pages": stats.unchanged_pages,
                "failed_pages": stats.failed_pages,
                "access_denied_pages": stats.access_denied_pages,
                "document_links": stats.document_links,
                "external_links": stats.external_links,
                "duplicate_links": stats.duplicate_links,
                "robots_blocked": stats.robots_blocked,
                "non_html_skipped": stats.non_html_skipped,
                "max_depth_reached": stats.max_depth_reached,
            },
            "successful_urls": self.state.successful,
            "failed_urls": self.state.failed,
            "skipped_urls": self.state.skipped,
            "document_urls": sorted(self.state.document_links),
            "external_urls": sorted(self.state.external_links),
            "duplicate_urls": sorted(self.state.duplicates),
            "robots": {
                "enabled": self.robots.enabled,
                "available": self.robots.available,
                "robots_url": self.robots.robots_url,
                "fetch_error": self.robots.fetch_error,
            },
        }

        report_path = self.run_dir / "crawl_report.json"
        failed_path = self.run_dir / "failed_urls.json"
        skipped_path = self.run_dir / "skipped_urls.json"
        stats_path = self.run_dir / "crawl_stats.json"

        _write_json(report_path, report)
        _write_json(failed_path, self.state.failed)
        _write_json(skipped_path, self.state.skipped)
        _write_json(stats_path, asdict(stats))
        return report_path


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Crawl BMI Hub with interactive Playwright authentication."
    )
    parser.add_argument(
        "--mode",
        choices=("full", "incremental"),
        default=None,
        help="full = recrawl discovered pages; incremental = new/changed/failed only.",
    )
    parser.add_argument(
        "--reauth",
        action="store_true",
        help="Force interactive login and overwrite saved Playwright storage state.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Maximum number of pages to crawl successfully.",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=None,
        help="Maximum link depth from the start URL.",
    )
    parser.add_argument(
        "--start-url",
        type=str,
        default=None,
        help="Override start URL (must match CRAWLER_ALLOWED_HOSTS / start-url host).",
    )
    parser.add_argument(
        "--seed-url",
        action="append",
        default=[],
        help="Additional seed URL (repeatable). Used for targeted / query-time crawls.",
    )
    parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="Reuse saved session only; fail if login is required.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run Chromium headed during the crawl (login always uses headed mode).",
    )
    parser.add_argument(
        "--ignore-robots",
        action="store_true",
        help="Do not fetch/enforce robots.txt (still stays on the BMI Hub domain).",
    )
    return parser


async def async_main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    settings = CrawlerSettings.from_env()

    if args.max_pages is not None:
        settings = replace(settings, max_pages=args.max_pages)
    if args.max_depth is not None:
        settings = replace(settings, max_depth=args.max_depth)
    if args.start_url:
        settings = replace(settings, start_url=args.start_url)
    if args.headed:
        settings = replace(settings, headless=False)
    if args.ignore_robots:
        settings = replace(settings, respect_robots=False)
    if args.mode:
        settings = replace(settings, crawl_mode=args.mode)

    crawler = BmiHubCrawler(
        settings,
        force_reauth=args.reauth,
        mode=args.mode,
        seed_urls=args.seed_url,
        allow_interactive=not args.no_interactive,
    )
    try:
        await crawler.run()
    except AuthenticationError as exc:
        print(f"Authentication failed: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Crawl interrupted by user.", file=sys.stderr)
        return 130
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
