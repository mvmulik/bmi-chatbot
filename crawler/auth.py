"""Interactive Playwright authentication using the employee's normal BMI Hub login.

This module never collects passwords, MFA codes, cookies for logging, or tokens.
The user completes sign-in (including MFA) in a headed browser.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import Browser, BrowserContext, Page, TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from crawler.auth_signals import (
    looks_like_login_url,
    looks_like_sign_in_title,
    parse_auth_selectors,
)
from crawler.config import CrawlerSettings, get_allowed_hosts
from crawler.logutil import log_path, logger, redact

AUTH_REQUIRED_MESSAGE = (
    "Authentication Required\n"
    "Please complete the normal BMI Hub login in the browser window.\n"
    "Complete MFA if prompted. Do not share your password or codes with this crawler.\n"
    "The crawler continues automatically once it sees BMI Hub (not the sign-in page)."
)

PASSWORD_SELECTORS = (
    'input[type="password"]',
    'input[name="passwd"]',
    "#i0118",
    "#passwordInput",
)


class AuthenticationError(RuntimeError):
    """Raised when interactive authentication cannot be completed."""


def ensure_auth_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def storage_state_exists(settings: CrawlerSettings) -> bool:
    return settings.storage_state_path.is_file() and settings.storage_state_path.stat().st_size > 0


def _auth_selectors(settings: CrawlerSettings) -> tuple[str, ...]:
    return parse_auth_selectors(settings.auth_selectors)


def _context_kwargs(settings: CrawlerSettings) -> dict[str, object]:
    return {
        "user_agent": settings.user_agent,
        "ignore_https_errors": settings.ignore_https_errors,
    }


async def _selector_visible(page: Page, selector: str) -> bool:
    try:
        locator = page.locator(selector)
        count = await locator.count()
        if count <= 0:
            return False
        return bool(await locator.first.is_visible())
    except Exception:  # noqa: BLE001 - invalid/unstable selectors must not crash auth
        return False


async def _login_form_visible(page: Page) -> bool:
    for selector in PASSWORD_SELECTORS:
        if await _selector_visible(page, selector):
            return True
    return False


async def is_authenticated(page: Page, settings: CrawlerSettings) -> bool:
    """True when the browser is on BMI Hub and not on a login/MFA surface.

    HTTP 200 is not treated as proof of authentication.
    """
    url = page.url or ""
    if looks_like_login_url(url, get_allowed_hosts()):
        return False
    if await _login_form_visible(page):
        return False

    try:
        title = await page.title()
    except Exception:  # noqa: BLE001
        title = ""
    if looks_like_sign_in_title(title):
        return False

    for selector in _auth_selectors(settings):
        if await _selector_visible(page, selector):
            return True

    try:
        text = (await page.locator("body").inner_text(timeout=2_000)).strip()
    except Exception:  # noqa: BLE001
        text = ""
    # Hub home after SSO often has no M365 suite bar; require real page text.
    return len(text) >= 80


async def wait_for_login(page: Page, settings: CrawlerSettings) -> bool:
    """Wait for Hub content after the user completes normal login/MFA."""
    timeout_ms = max(5_000, settings.auth_timeout_ms)
    interval_ms = 1_000
    elapsed = 0
    minutes = timeout_ms // 60_000
    print(f"Waiting up to {minutes} minute(s) for BMI Hub to appear after SSO/MFA...")
    while elapsed <= timeout_ms:
        if await is_authenticated(page, settings):
            logger.info("Authentication verified")
            return True
        if elapsed and elapsed % 15_000 == 0:
            logger.info("Waiting for BMI Hub login to finish (%s)", log_path(page.url))
        await page.wait_for_timeout(interval_ms)
        elapsed += interval_ms

    print(
        "Automatic detection timed out. If BMI Hub is already visible in the browser, "
        "press Enter to continue. Type q then Enter to cancel."
    )
    try:
        answer = await asyncio.to_thread(input, "> ")
    except Exception:  # noqa: BLE001
        return False
    if answer.strip().lower() in {"q", "quit", "cancel"}:
        return False
    if await is_authenticated(page, settings):
        logger.info("Authentication verified")
        return True
    url = page.url or ""
    if looks_like_login_url(url, get_allowed_hosts()) or await _login_form_visible(page):
        logger.warning("Browser is still on a sign-in page after confirmation")
        return False
    host = (urlparse(url).hostname or "").lower()
    if host in get_allowed_hosts():
        logger.info("Authentication verified after operator confirmation")
        return True
    return False


async def _open_hub(page: Page, settings: CrawlerSettings) -> None:
    page.set_default_timeout(min(settings.navigation_timeout_ms, 60_000))
    try:
        await page.goto(
            settings.start_url,
            wait_until="domcontentloaded",
            timeout=settings.navigation_timeout_ms,
        )
    except PlaywrightTimeoutError:
        logger.warning("BMI Hub navigation timed out; continuing with the current page")


async def interactive_login(settings: CrawlerSettings) -> Path:
    """Open a headed browser so the employee can sign in normally, then save storage state."""
    ensure_auth_dir(settings.auth_dir)
    storage_path = settings.storage_state_path

    logger.info("Authentication required")
    print()
    print("=" * 72)
    print(AUTH_REQUIRED_MESSAGE)
    print("=" * 72)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False)
        context = await browser.new_context(**_context_kwargs(settings))
        page = await context.new_page()
        try:
            await _open_hub(page, settings)
            authenticated = await wait_for_login(page, settings)
            if not authenticated:
                raise AuthenticationError(
                    "BMI Hub login was not completed within the authentication timeout. "
                    "The crawler did not save a session. Re-run the crawl and finish SSO/MFA "
                    "in the browser, then press Enter when you see BMI Hub."
                )
            await context.storage_state(path=str(storage_path))
            logger.info("Authentication successful")
        finally:
            await context.close()
            await browser.close()

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
            "No authorized BMI Hub session is saved. Complete the normal login in the browser first."
        )

    return await browser.new_context(
        storage_state=str(settings.storage_state_path),
        **_context_kwargs(settings),
    )


async def refresh_storage_state(context: BrowserContext, settings: CrawlerSettings) -> None:
    """Persist the current authorized browser state. Never log the file contents."""
    ensure_auth_dir(settings.auth_dir)
    await context.storage_state(path=str(settings.storage_state_path))


async def probe_authenticated_session(page: Page, settings: CrawlerSettings) -> bool:
    """Navigate to BMI Hub and verify the session without treating HTTP 200 as success."""
    try:
        await _open_hub(page, settings)
        ok = await is_authenticated(page, settings)
        if ok:
            logger.info("Authentication verified")
        else:
            logger.info("Saved session is not signed in to BMI Hub yet")
        return ok
    except Exception as exc:  # noqa: BLE001 - probe should never crash the CLI
        logger.warning("Authentication check failed: %s", redact(str(exc)))
        return False


async def ensure_authenticated(page: Page, settings: CrawlerSettings) -> bool:
    if await is_authenticated(page, settings):
        return True
    logger.info("BMI Hub sign-in is required")
    print(AUTH_REQUIRED_MESSAGE)
    try:
        await _open_hub(page, settings)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not open BMI Hub for re-authentication: %s", redact(str(exc)))
        return False
    return await wait_for_login(page, settings)
