"""Configuration for the BMI Hub crawler."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")

DEFAULT_START_URL = "https://bmihub.burnsmcd.com/"
ALLOWED_HOSTS = frozenset({"bmihub.burnsmcd.com"})


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
