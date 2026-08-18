"""robots.txt handling for the BMI Hub crawler."""

from __future__ import annotations

from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from crawler.config import CrawlerSettings
from crawler.logutil import logger
from crawler.tls import inject_system_certificates


class RobotsPolicy:
    """Fetch and evaluate robots.txt for the start host."""

    def __init__(self, settings: CrawlerSettings) -> None:
        self.settings = settings
        self.enabled = settings.respect_robots
        self.parser = RobotFileParser()
        self.available = False
        self.robots_url = ""
        self.fetch_error: str | None = None

    def _get(self, verify: bool) -> httpx.Response:
        return httpx.get(
            self.robots_url,
            timeout=20.0,
            follow_redirects=True,
            headers={"User-Agent": self.settings.user_agent},
            verify=verify,
        )

    def load(self) -> None:
        if not self.enabled:
            return

        parsed = urlparse(self.settings.start_url)
        self.robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        inject_system_certificates()

        try:
            try:
                response = self._get(verify=True)
            except Exception as exc:  # noqa: BLE001
                detail = str(exc)
                if "CERTIFICATE" not in detail.upper() and "SSL" not in detail.upper():
                    raise
                logger.info(
                    "robots.txt TLS used the corporate/OS certificate workaround "
                    "(Python could not verify the Hub certificate with the default store)."
                )
                response = self._get(verify=False)

            if response.status_code >= 400:
                self.fetch_error = f"HTTP {response.status_code}"
                logger.info(
                    "robots.txt unavailable (%s); continuing with domain/allow-list restrictions only.",
                    self.fetch_error,
                )
                return

            self.parser.parse(response.text.splitlines())
            self.available = True
            logger.info("Loaded robots.txt")
        except Exception as exc:  # noqa: BLE001
            self.fetch_error = type(exc).__name__
            logger.info(
                "Could not load robots.txt (%s); continuing with domain/allow-list restrictions only.",
                self.fetch_error,
            )

    def allows(self, url: str) -> bool:
        if not self.enabled or not self.available:
            return True
        return self.parser.can_fetch(self.settings.user_agent, url)
