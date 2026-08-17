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
)
from crawler.config import CrawlerSettings
from crawler.extractor import (
    extract_page_content,
    is_internal_url,
    is_probably_html_url,
    normalize_url,
    utc_now_iso,
)
from crawler.robots import RobotsPolicy


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


class BmiHubCrawler:
    def __init__(self, settings: CrawlerSettings, *, force_reauth: bool = False) -> None:
        self.settings = settings
        self.force_reauth = force_reauth
        self.robots = RobotsPolicy(settings)
        self.state = CrawlState()
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

    async def run(self) -> Path:
        self.settings.output_dir.mkdir(parents=True, exist_ok=True)
        self.pages_dir.mkdir(parents=True, exist_ok=True)
        self.robots.load()

        start = normalize_url(self.settings.start_url)
        if not start or not is_internal_url(start):
            raise ValueError(f"Invalid start URL: {self.settings.start_url}")

        self._enqueue(start, 0, source="seed")

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=self.settings.headless)
            try:
                context = await create_authenticated_context(
                    browser,
                    self.settings,
                    force_reauth=self.force_reauth,
                )
                page = await context.new_page()
                page.set_default_timeout(self.settings.navigation_timeout_ms)

                if not await probe_authenticated_session(page, self.settings):
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

        report_path = self._write_report()
        print(f"Crawl complete. Report: {report_path}")
        return report_path

    async def _crawl_one(self, page: Any, url: str, depth: int) -> None:
        print(f"[{len(self.state.successful) + 1}/{self.settings.max_pages}] depth={depth} {url}")
        try:
            response = await page.goto(url, wait_until="domcontentloaded")
            status = response.status if response else None
            final_url = normalize_url(page.url) or page.url

            if status is not None and status >= 400:
                self.state.failed.append(
                    {
                        "url": url,
                        "final_url": final_url,
                        "error_type": "http_error",
                        "status_code": status,
                        "message": f"HTTP {status}",
                        "timestamp": utc_now_iso(),
                    }
                )
                self.state.stats.failed_pages += 1
                return

            html = await page.content()
            extracted = extract_page_content(
                url=url,
                final_url=final_url,
                html=html,
                status_code=status,
            )
            extracted["depth"] = depth

            out_path = self.pages_dir / f"{_slug_for_url(url)}.json"
            _write_json(out_path, extracted)

            self.state.successful.append(url)
            self.state.stats.successfully_crawled_pages += 1

            for link in extracted.get("links", []):
                link_url = link.get("url", "")
                self._enqueue(link_url, depth + 1, source=url)

        except (PlaywrightTimeoutError, PlaywrightError) as exc:
            self.state.failed.append(
                {
                    "url": url,
                    "error_type": "playwright_error",
                    "message": str(exc),
                    "timestamp": utc_now_iso(),
                }
            )
            self.state.stats.failed_pages += 1
        except Exception as exc:  # noqa: BLE001 - record unexpected page failures
            self.state.failed.append(
                {
                    "url": url,
                    "error_type": "unexpected_error",
                    "message": str(exc),
                    "timestamp": utc_now_iso(),
                }
            )
            self.state.stats.failed_pages += 1

    def _write_report(self) -> Path:
        stats = self.state.stats
        report = {
            "started_from": self.settings.start_url,
            "run_directory": str(self.run_dir),
            "generated_at": utc_now_iso(),
            "settings": {
                "max_pages": self.settings.max_pages,
                "max_depth": self.settings.max_depth,
                "request_delay_seconds": self.settings.request_delay_seconds,
                "respect_robots": self.settings.respect_robots,
                "headless": self.settings.headless,
            },
            "totals": {
                "total_pages_discovered": stats.total_pages_discovered,
                "successfully_crawled_pages": stats.successfully_crawled_pages,
                "failed_pages": stats.failed_pages,
                "skipped_pages": stats.skipped_pages,
                "external_links": stats.external_links,
                "duplicate_links": stats.duplicate_links,
                "robots_blocked": stats.robots_blocked,
                "non_html_skipped": stats.non_html_skipped,
                "max_depth_reached": stats.max_depth_reached,
            },
            "successful_urls": self.state.successful,
            "failed_urls": self.state.failed,
            "skipped_urls": self.state.skipped,
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

    crawler = BmiHubCrawler(settings, force_reauth=args.reauth)
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
