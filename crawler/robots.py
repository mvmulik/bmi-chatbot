"""robots.txt handling for the BMI Hub crawler."""

from __future__ import annotations

import sys
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from crawler.config import CrawlerSettings


class RobotsPolicy:
    """Fetch and evaluate robots.txt for the start host."""

    def __init__(self, settings: CrawlerSettings) -> None:
        self.settings = settings
        self.enabled = settings.respect_robots
        self.parser = RobotFileParser()
        self.available = False
        self.robots_url = ""
        self.fetch_error: str | None = None

    def load(self) -> None:
        if not self.enabled:
            return

        parsed = urlparse(self.settings.start_url)
        self.robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

        try:
            response = httpx.get(
                self.robots_url,
                timeout=20.0,
                follow_redirects=True,
                headers={"User-Agent": self.settings.user_agent},
            )
            if response.status_code >= 400:
                self.fetch_error = f"HTTP {response.status_code}"
                print(
                    f"robots.txt unavailable ({self.fetch_error}); continuing with "
                    "domain/allow-list restrictions only.",
                    file=sys.stderr,
                )
                return

            self.parser.parse(response.text.splitlines())
            self.available = True
            print(f"Loaded robots.txt from {self.robots_url}")
        except Exception as exc:  # noqa: BLE001
            self.fetch_error = str(exc)
            print(
                f"Could not load robots.txt ({self.fetch_error}); continuing with "
                "domain/allow-list restrictions only.",
                file=sys.stderr,
            )

    def allows(self, url: str) -> bool:
        if not self.enabled or not self.available:
            return True
        return self.parser.can_fetch(self.settings.user_agent, url)
