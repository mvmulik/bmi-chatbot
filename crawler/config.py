"""Configuration for the BMI Hub crawler."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")

# Default only for local convenience; override via CRAWLER_START_URL in every environment.
DEFAULT_START_URL = "https://bmihub.burnsmcd.com/"


def get_allowed_hosts() -> frozenset[str]:
    """Hosts permitted for crawl discovery (comma-separated or derived from start URL)."""
    raw = os.getenv("CRAWLER_ALLOWED_HOSTS", "").strip()
    if raw:
        return frozenset(host.strip().lower() for host in raw.split(",") if host.strip())

    start_url = os.getenv("CRAWLER_START_URL", DEFAULT_START_URL).strip() or DEFAULT_START_URL
    hostname = urlparse(start_url).hostname
    if hostname:
        return frozenset({hostname.lower()})
    return frozenset()


# Backwards-compatible name used by extractor/tests.
ALLOWED_HOSTS = get_allowed_hosts()


@dataclass(frozen=True)
class CrawlerSettings:
    start_url: str = DEFAULT_START_URL
    max_pages: int = 200
    max_depth: int = 8
    request_delay_seconds: float = 0.75
    navigation_timeout_ms: int = 60_000
    output_dir: Path = ROOT_DIR / "data" / "raw"
    auth_dir: Path = ROOT_DIR / "data" / "auth"
    storage_state_path: Path = ROOT_DIR / "data" / "auth" / "playwright_storage_state.json"
    user_agent: str = (
        "BMIHubCrawler/0.1 (+internal research; contact local owner; respects robots.txt)"
    )
    respect_robots: bool = True
    headless: bool = True

    @classmethod
    def from_env(cls) -> CrawlerSettings:
        return cls(
            start_url=os.getenv("CRAWLER_START_URL", DEFAULT_START_URL).strip()
            or DEFAULT_START_URL,
            max_pages=int(os.getenv("CRAWLER_MAX_PAGES", "200")),
            max_depth=int(os.getenv("CRAWLER_MAX_DEPTH", "8")),
            request_delay_seconds=float(os.getenv("CRAWLER_DELAY_SECONDS", "0.75")),
            navigation_timeout_ms=int(os.getenv("CRAWLER_NAVIGATION_TIMEOUT_MS", "60000")),
            output_dir=Path(
                os.getenv("CRAWLER_OUTPUT_DIR", str(ROOT_DIR / "data" / "raw"))
            ),
            auth_dir=Path(os.getenv("CRAWLER_AUTH_DIR", str(ROOT_DIR / "data" / "auth"))),
            storage_state_path=Path(
                os.getenv(
                    "CRAWLER_STORAGE_STATE_PATH",
                    str(ROOT_DIR / "data" / "auth" / "playwright_storage_state.json"),
                )
            ),
            respect_robots=os.getenv("CRAWLER_RESPECT_ROBOTS", "true").lower()
            in {"1", "true", "yes"},
            headless=os.getenv("CRAWLER_HEADLESS", "true").lower() in {"1", "true", "yes"},
        )
