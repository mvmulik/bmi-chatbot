"""Authentication UI/URL signals that do not inspect credentials or tokens."""

from __future__ import annotations

from urllib.parse import urlparse

from crawler.config import get_allowed_hosts

LOGIN_HOST_HINTS = (
    "login.microsoftonline.com",
    "login.windows.net",
    "sts.windows.net",
    "adfs",
)
LOGIN_PATH_HINTS = (
    "login",
    "signin",
    "sign-in",
    "signout",
    "logoff",
    "/adfs/",
    "oauth",
    "saml",
    "auth",
)
SIGN_IN_TITLES = (
    "sign in",
    "sign-in",
    "log in",
    "login",
    "pick an account",
    "enter password",
    "verify your identity",
)
ACCESS_DENIED_HINTS = (
    "access denied",
    "401 unauthorized",
    "403 forbidden",
    "you don't have access",
    "you do not have access",
    "request access",
    "access restricted",
)

# Specific Hub/M365 chrome only — do not include generic `header`/`nav` (those appear on login pages).
DEFAULT_AUTH_SELECTORS = (
    "#O365_MainLink_Me",
    "#meInitialsButton",
    "#SuiteNavWrapper",
    "#O365_Header",
    "#spSiteHeader",
    "#sp-appBar",
    "[data-automationid='SiteHeader']",
    "button[aria-label*='Account' i]",
    "a[aria-label*='Sign out' i]",
    "a[href*='logout' i]",
    "a[href*='signout' i]",
    "#mectrl_main_trigger",
    ".o365sx-navbar",
    "[data-automation-id='SimpleSiteHeader']",
)


def looks_like_sign_in_title(title: str) -> bool:
    lowered = (title or "").strip().lower()
    if not lowered:
        return False
    return any(token in lowered for token in SIGN_IN_TITLES)


def looks_like_login_url(url: str, allowed_hosts: frozenset[str] | None = None) -> bool:
    """True when the browser is on an IdP/login surface, not authenticated BMI Hub."""
    parsed = urlparse(url or "")
    host = (parsed.hostname or "").lower()
    allowed = allowed_hosts if allowed_hosts is not None else get_allowed_hosts()
    if host in LOGIN_HOST_HINTS or any(hint in host for hint in LOGIN_HOST_HINTS):
        return True
    if allowed and host not in allowed:
        return True
    haystack = f"{host}{parsed.path}".lower()
    if host in allowed:
        path = parsed.path.lower()
        return any(
            hint in path
            for hint in ("login", "signin", "sign-in", "/adfs/", "authenticate.aspx")
        )
    return any(hint in haystack for hint in LOGIN_PATH_HINTS)


def looks_like_access_denied(
    *,
    status: int | None,
    page_url: str,
    title: str,
    html_excerpt: str,
) -> bool:
    if status in {401, 403}:
        return True
    haystack = f"{page_url} {title} {html_excerpt[:2000]}".lower()
    return any(marker in haystack for marker in ACCESS_DENIED_HINTS)


def parse_auth_selectors(raw: str | None) -> tuple[str, ...]:
    if not raw or not raw.strip():
        return DEFAULT_AUTH_SELECTORS
    selectors = tuple(item.strip() for item in raw.split(",") if item.strip())
    return selectors or DEFAULT_AUTH_SELECTORS
