"""HTML cleaning and structured text extraction for RAG preprocessing."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup, NavigableString, Tag

NOISE_TAGS = {
    "script",
    "style",
    "noscript",
    "template",
    "svg",
    "iframe",
    "canvas",
    "form",
    "button",
    "input",
    "select",
    "textarea",
    "img",
    "picture",
    "video",
    "audio",
    "source",
}

NAV_FOOTER_TAGS = {"nav", "footer", "aside"}

NAV_FOOTER_ATTR_HINTS = (
    "nav",
    "menu",
    "navbar",
    "sidebar",
    "breadcrumb",
    "footer",
    "cookie",
    "banner",
    "masthead",
    "toolbar",
    "skiplink",
    "skip-link",
)

FOOTER_TEXT_HINTS = (
    "copyright",
    "all rights reserved",
    "privacy policy",
    "terms of use",
    "cookie settings",
    "follow us",
)


@dataclass
class ContentBlock:
    """A logical content block used for section-aware chunking."""

    kind: str  # heading | paragraph | list | table | link
    text: str
    heading: str = ""
    section: str = ""
    level: int = 0


@dataclass
class CleanedDocument:
    url: str
    page_title: str
    crawl_timestamp: str
    cleaned_text: str
    blocks: list[ContentBlock] = field(default_factory=list)
    preserved_links: list[dict[str, str]] = field(default_factory=list)


def _attr_blob(tag: Tag) -> str:
    parts: list[str] = []
    for key in ("id", "class", "role", "aria-label", "name"):
        value = tag.get(key)
        if isinstance(value, list):
            parts.extend(str(v) for v in value)
        elif value:
            parts.append(str(value))
    return " ".join(parts).lower()


def _looks_like_chrome(tag: Tag) -> bool:
    if tag.name in NAV_FOOTER_TAGS:
        return True
    role = str(tag.get("role", "")).lower()
    if role in {"navigation", "contentinfo", "banner", "complementary"}:
        return True
    blob = _attr_blob(tag)
    return any(hint in blob for hint in NAV_FOOTER_ATTR_HINTS)


def _is_footer_boilerplate(text: str) -> bool:
    lowered = text.lower().strip()
    if not lowered:
        return True
    if len(lowered) < 120 and any(hint in lowered for hint in FOOTER_TEXT_HINTS):
        return True
    if re.fullmatch(r"(©|\(c\)).*", lowered):
        return True
    return False


def _normalize_whitespace(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [line.strip() for line in text.splitlines()]
    # Drop empty lines at edges; keep single blank lines between blocks.
    compact: list[str] = []
    previous_blank = False
    for line in lines:
        blank = line == ""
        if blank and previous_blank:
            continue
        compact.append(line)
        previous_blank = blank
    return "\n".join(compact).strip()


def _dedupe_consecutive_lines(text: str) -> str:
    lines = text.splitlines()
    result: list[str] = []
    seen_recent: set[str] = set()
    window: list[str] = []
    for line in lines:
        key = line.strip().lower()
        if key and key in seen_recent and len(key) < 120:
            # Likely repeated nav/menu labels.
            continue
        result.append(line)
        if key:
            window.append(key)
            seen_recent.add(key)
            if len(window) > 40:
                old = window.pop(0)
                if old not in window:
                    seen_recent.discard(old)
    return "\n".join(result)


def _main_content_root(soup: BeautifulSoup) -> Tag:
    for selector in ("main", "[role='main']", "article", "#content", ".content", "#main"):
        node = soup.select_one(selector)
        if node is not None:
            return node
    body = soup.body
    return body if body is not None else soup


def _strip_noise(root: Tag) -> None:
    for tag in list(root.find_all(True)):
        if not isinstance(tag, Tag):
            continue
        if tag.name in NOISE_TAGS:
            tag.decompose()
            continue
        if _looks_like_chrome(tag):
            tag.decompose()


def _serialize_link(tag: Tag, base_url: str) -> str | None:
    href = str(tag.get("href", "")).strip()
    label = " ".join(tag.get_text(" ", strip=True).split())
    if not label:
        return None
    if href.startswith(("javascript:", "mailto:", "tel:", "#")):
        return label
    absolute = urljoin(base_url, href) if href else ""
    if absolute and absolute.startswith(("http://", "https://")):
        return f"[{label}]({absolute})"
    return label


def _serialize_list(tag: Tag, base_url: str) -> str:
    lines: list[str] = []
    ordered = tag.name == "ol"
    index = 1
    for li in tag.find_all("li", recursive=False):
        parts: list[str] = []
        for child in li.children:
            if isinstance(child, NavigableString):
                value = " ".join(str(child).split())
                if value:
                    parts.append(value)
            elif isinstance(child, Tag):
                if child.name == "a":
                    link = _serialize_link(child, base_url)
                    if link:
                        parts.append(link)
                elif child.name in {"ul", "ol"}:
                    nested = _serialize_list(child, base_url)
                    if nested:
                        parts.append("\n" + nested)
                else:
                    value = " ".join(child.get_text(" ", strip=True).split())
                    if value:
                        parts.append(value)
        item = " ".join(parts).strip()
        if not item:
            continue
        prefix = f"{index}. " if ordered else "- "
        lines.append(prefix + item)
        index += 1
    return "\n".join(lines)


def _serialize_table(tag: Tag, base_url: str) -> str:
    rows: list[str] = []
    for tr in tag.find_all("tr"):
        cells: list[str] = []
        for cell in tr.find_all(["th", "td"], recursive=False):
            cell_parts: list[str] = []
            for child in cell.children:
                if isinstance(child, NavigableString):
                    value = " ".join(str(child).split())
                    if value:
                        cell_parts.append(value)
                elif isinstance(child, Tag) and child.name == "a":
                    link = _serialize_link(child, base_url)
                    if link:
                        cell_parts.append(link)
                elif isinstance(child, Tag):
                    value = " ".join(child.get_text(" ", strip=True).split())
                    if value:
                        cell_parts.append(value)
            cells.append(" ".join(cell_parts).strip())
        if any(cells):
            rows.append(" | ".join(cells))
    return "\n".join(rows)


def _iter_content_blocks(root: Tag, base_url: str) -> list[ContentBlock]:
    blocks: list[ContentBlock] = []
    heading_stack: list[str] = []
    current_heading = ""
    current_section = ""

    skip_names = {"script", "style"}

    for element in root.descendants:
        if not isinstance(element, Tag):
            continue
        if element.name in skip_names:
            continue

        # Avoid double-processing nested list/table nodes.
        if element.name in {"li", "tr", "th", "td", "thead", "tbody", "tfoot"}:
            continue

        if element.name in {f"h{i}" for i in range(1, 7)}:
            level = int(element.name[1])
            text = " ".join(element.get_text(" ", strip=True).split())
            if not text:
                continue
            heading_stack = [h for h in heading_stack[: level - 1]]
            heading_stack.append(text)
            current_heading = text
            current_section = " > ".join(heading_stack)
            blocks.append(
                ContentBlock(
                    kind="heading",
                    text=f"{'#' * level} {text}",
                    heading=current_heading,
                    section=current_section,
                    level=level,
                )
            )
            continue

        if element.name in {"ul", "ol"}:
            # Only process outermost lists.
            parent_list = element.find_parent(["ul", "ol"])
            if parent_list is not None:
                continue
            text = _serialize_list(element, base_url)
            text = _normalize_whitespace(text)
            if text and not _is_footer_boilerplate(text):
                blocks.append(
                    ContentBlock(
                        kind="list",
                        text=text,
                        heading=current_heading,
                        section=current_section or current_heading,
                    )
                )
            continue

        if element.name == "table":
            text = _serialize_table(element, base_url)
            text = _normalize_whitespace(text)
            if text and not _is_footer_boilerplate(text):
                blocks.append(
                    ContentBlock(
                        kind="table",
                        text=text,
                        heading=current_heading,
                        section=current_section or current_heading,
                    )
                )
            continue

        if element.name in {"p", "div", "section", "article"}:
            # Prefer leaf-ish text containers: skip if it contains nested block tags we handle.
            if element.find(["p", "div", "ul", "ol", "table", "h1", "h2", "h3", "h4", "h5", "h6"]):
                # Still capture direct text+links if meaningful and no nested handled blocks
                # except for div wrappers; skip nested containers.
                if element.name != "p":
                    continue

            parts: list[str] = []
            for child in element.children:
                if isinstance(child, NavigableString):
                    value = " ".join(str(child).split())
                    if value:
                        parts.append(value)
                elif isinstance(child, Tag) and child.name == "a":
                    link = _serialize_link(child, base_url)
                    if link:
                        parts.append(link)
                elif isinstance(child, Tag) and child.name not in {
                    "ul",
                    "ol",
                    "table",
                    "h1",
                    "h2",
                    "h3",
                    "h4",
                    "h5",
                    "h6",
                }:
                    value = " ".join(child.get_text(" ", strip=True).split())
                    if value:
                        parts.append(value)

            text = _normalize_whitespace(" ".join(parts))
            if text and not _is_footer_boilerplate(text):
                blocks.append(
                    ContentBlock(
                        kind="paragraph",
                        text=text,
                        heading=current_heading,
                        section=current_section or current_heading,
                    )
                )

    return blocks


def clean_html(
    html: str,
    *,
    url: str = "",
    page_title: str = "",
    crawl_timestamp: str = "",
) -> CleanedDocument:
    soup = BeautifulSoup(html, "lxml")
    title = page_title or " ".join(
        (soup.title.get_text(" ", strip=True) if soup.title else "").split()
    )
    root = _main_content_root(soup)
    _strip_noise(root)

    blocks = _iter_content_blocks(root, url)
    # Deduplicate identical consecutive paragraph/list blocks (nav leftovers).
    deduped: list[ContentBlock] = []
    seen_text: set[str] = set()
    for block in blocks:
        key = block.text.strip().lower()
        if block.kind != "heading" and key in seen_text and len(key) < 180:
            continue
        if block.kind != "heading":
            seen_text.add(key)
        deduped.append(block)

    cleaned_text = _normalize_whitespace("\n\n".join(b.text for b in deduped if b.text))
    cleaned_text = _dedupe_consecutive_lines(cleaned_text)
    cleaned_text = _normalize_whitespace(cleaned_text)

    links: list[dict[str, str]] = []
    for match in re.finditer(r"\[([^\]]+)\]\((https?://[^)]+)\)", cleaned_text):
        links.append({"text": match.group(1), "url": match.group(2)})

    return CleanedDocument(
        url=url,
        page_title=title,
        crawl_timestamp=crawl_timestamp,
        cleaned_text=cleaned_text,
        blocks=deduped,
        preserved_links=links,
    )


def clean_from_crawled_page(page: dict[str, Any]) -> CleanedDocument:
    """Clean a crawled page JSON record, preferring raw HTML when present."""
    url = str(page.get("final_url") or page.get("url") or "")
    title = str(page.get("page_title") or "")
    timestamp = str(page.get("crawl_timestamp") or "")
    html = page.get("html")

    if isinstance(html, str) and html.strip():
        return clean_html(
            html,
            url=url,
            page_title=title,
            crawl_timestamp=timestamp,
        )

    # Fallback for older crawl artifacts without HTML.
    parts: list[str] = []
    if title:
        parts.append(f"# {title}")
    for heading in page.get("headings") or []:
        if isinstance(heading, dict) and heading.get("text"):
            level = str(heading.get("level", "h2")).lstrip("h")
            try:
                hashes = int(level)
            except ValueError:
                hashes = 2
            parts.append(f"{'#' * max(1, min(hashes, 6))} {heading['text']}")
    visible = str(page.get("visible_text") or "").strip()
    if visible:
        parts.append(visible)
    for link in page.get("links") or []:
        if not isinstance(link, dict):
            continue
        if not link.get("internal"):
            continue
        label = str(link.get("text") or "").strip()
        href = str(link.get("url") or "").strip()
        if label and href:
            parts.append(f"[{label}]({href})")

    cleaned = _normalize_whitespace("\n\n".join(parts))
    blocks = [
        ContentBlock(
            kind="paragraph",
            text=cleaned,
            heading=title,
            section=title,
        )
    ] if cleaned else []
    return CleanedDocument(
        url=url,
        page_title=title,
        crawl_timestamp=timestamp,
        cleaned_text=cleaned,
        blocks=blocks,
        preserved_links=[],
    )
