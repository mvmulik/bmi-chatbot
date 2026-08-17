"""Interactive Playwright authentication and storage-state management."""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from crawler.config import CrawlerSettings, get_allowed_hosts


class AuthenticationError(RuntimeError):
    """Raised when interactive authentication cannot be completed."""


def ensure_auth_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def storage_state_exists(settings: CrawlerSettings) -> bool:
    return settings.storage_state_path.is_file() and settings.storage_state_path.stat().st_size > 0


async def interactive_login(settings: CrawlerSettings) -> Path:
    """Open a headed browser so the user can sign in manually, then persist storage state."""
    ensure_auth_dir(settings.auth_dir)
    storage_path = settings.storage_state_path

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False)
        context = await browser.new_context(user_agent=settings.user_agent)
        page = await context.new_page()
        page.set_default_timeout(settings.navigation_timeout_ms)

        print(f"Opening login page: {settings.start_url}")
        await page.goto(settings.start_url, wait_until="domcontentloaded")

        print()
        print("=" * 72)
        print("Interactive authentication required")
        print("1. Complete sign-in in the browser window that just opened.")
        print("2. Wait until you can see authenticated BMI Hub content.")
        print("3. Return here and press Enter to save the session.")
        print("   (Type 'q' then Enter to cancel.)")
        print("=" * 72)

        response = input("> ").strip().lower()
        if response in {"q", "quit", "cancel"}:
            await context.close()
            await browser.close()
            raise AuthenticationError("Authentication cancelled by user.")

        await context.storage_state(path=str(storage_path))
        await context.close()
        await browser.close()

    print(f"Saved Playwright storage state to: {storage_path}")
    return storage_path


async def create_authenticated_context(
    browser: Browser,
    settings: CrawlerSettings,
    *,
    force_reauth: bool = False,
) -> BrowserContext:
    """Create a browser context, reusing saved storage state when available."""
    if force_reauth or not storage_state_exists(settings):
        await interactive_login(settings)

    if not storage_state_exists(settings):
        raise AuthenticationError(
            f"Storage state not found at {settings.storage_state_path}. "
            "Run authentication first."
        )

    context = await browser.new_context(
        storage_state=str(settings.storage_state_path),
        user_agent=settings.user_agent,
    )
    return context


async def refresh_storage_state(context: BrowserContext, settings: CrawlerSettings) -> None:
    """Persist the current context cookies/local storage for future crawls."""
    ensure_auth_dir(settings.auth_dir)
    await context.storage_state(path=str(settings.storage_state_path))


async def probe_authenticated_session(page: Page, settings: CrawlerSettings) -> bool:
    """Best-effort check that the saved session can open the start URL."""
    try:
        response = await page.goto(settings.start_url, wait_until="domcontentloaded")
        if response is None:
            return False
        status = response.status
        url = page.url.lower()
        if status >= 400:
            return False
        # Common SSO / login markers — not definitive, but useful.
        login_markers = ("login", "signin", "sign-in", "adfs", "oauth", "saml", "auth")
        if any(marker in url for marker in login_markers):
            allowed = get_allowed_hosts()
            if not any(host in url for host in allowed):
                return False
        return True
    except Exception as exc:  # noqa: BLE001 - probe should never crash the CLI
        print(f"Session probe failed: {exc}", file=sys.stderr)
        return False
