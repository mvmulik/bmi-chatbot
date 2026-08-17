"""URL helpers and page content extraction for crawled HTML."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urldefrag, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup, NavigableString, Tag

from crawler.config import get_allowed_hosts


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_url(url: str, base_url: str | None = None) -> str | None:
    """Normalize a URL: resolve relative links, drop fragments, strip default ports."""
    if not url:
        return None

    candidate = url.strip()
    if not candidate or candidate.startswith(("javascript:", "mailto:", "tel:", "data:")):
        return None

    if base_url:
        candidate = urljoin(base_url, candidate)

    candidate, _fragment = urldefrag(candidate)
    parsed = urlparse(candidate)

    if parsed.scheme not in {"http", "https"}:
        return None
    if not parsed.netloc:
        return None

    host = parsed.hostname.lower() if parsed.hostname else ""
    netloc = host
    if parsed.port and parsed.port not in {80, 443}:
        netloc = f"{host}:{parsed.port}"

    path = parsed.path or "/"
    # Collapse duplicate slashes in path while preserving leading slash.
    while "//" in path:
        path = path.replace("//", "/")

    normalized = urlunparse(
        (
            parsed.scheme.lower(),
            netloc,
            path,
            "",
            parsed.query,
            "",
        )
    )
    return normalized


def is_internal_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return host in get_allowed_hosts()


def is_probably_html_url(url: str) -> bool:
    """Skip obvious binary/asset URLs during crawl discovery."""
    path = urlparse(url).path.lower()
    blocked_extensions = (
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".svg",
        ".webp",
        ".ico",
        ".css",
        ".js",
        ".map",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".mp4",
        ".mp3",
        ".zip",
        ".rar",
        ".7z",
        ".exe",
        ".dmg",
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
    )
    return not path.endswith(blocked_extensions)


def _visible_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "template", "svg"]):
        tag.decompose()

    texts: list[str] = []
    for element in soup.find_all(string=True):
        if not isinstance(element, NavigableString):
            continue
        parent = element.parent
        if isinstance(parent, Tag) and parent.name in {"script", "style"}:
            continue
        value = " ".join(str(element).split())
        if value:
            texts.append(value)
    return "\n".join(texts)


def _extract_headings(soup: BeautifulSoup) -> list[dict[str, str]]:
    headings: list[dict[str, str]] = []
    for level in range(1, 7):
        for node in soup.find_all(f"h{level}"):
            text = " ".join(node.get_text(" ", strip=True).split())
            if text:
                headings.append({"level": f"h{level}", "text": text})
    return headings


def _extract_links(soup: BeautifulSoup, page_url: str) -> list[dict[str, Any]]:
    links: list[dict[str, str]] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href", "")).strip()
        normalized = normalize_url(href, page_url)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        text = " ".join(anchor.get_text(" ", strip=True).split())
        links.append(
            {
                "url": normalized,
                "text": text,
                "internal": is_internal_url(normalized),
            }
        )
    return links


def _extract_navigation(soup: BeautifulSoup, page_url: str) -> list[dict[str, Any]]:
    nav_sections: list[dict[str, Any]] = []
    candidates = soup.find_all(["nav"]) + soup.select(
        "[role='navigation'], header nav, .nav, .menu, .navbar, .navigation"
    )

    seen_nodes: set[int] = set()
    for nav in candidates:
        node_id = id(nav)
        if node_id in seen_nodes:
            continue
        seen_nodes.add(node_id)

        items: list[dict[str, str]] = []
        for anchor in nav.find_all("a", href=True):
            href = str(anchor.get("href", "")).strip()
            normalized = normalize_url(href, page_url)
            if not normalized:
                continue
            items.append(
                {
                    "url": normalized,
                    "text": " ".join(anchor.get_text(" ", strip=True).split()),
                }
            )

        label = (
            nav.get("aria-label")
            or nav.get("id")
            or " ".join(nav.get("class", [])[:3])
            or nav.name
        )
        if items:
            nav_sections.append({"label": str(label), "items": items})

    return nav_sections


def extract_page_content(
    *,
    url: str,
    final_url: str,
    html: str,
    status_code: int | None,
) -> dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    title = " ".join((soup.title.get_text(" ", strip=True) if soup.title else "").split())
    links = _extract_links(soup, final_url or url)

    return {
        "url": url,
        "final_url": final_url,
        "status_code": status_code,
        "page_title": title,
        "headings": _extract_headings(soup),
        "visible_text": _visible_text(soup),
        "navigation": _extract_navigation(soup, final_url or url),
        "links": links,
        "html": html,
        "crawl_timestamp": utc_now_iso(),
    }
