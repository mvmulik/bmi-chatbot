"""Token-aware chunking for cleaned BMI Hub documents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from processor.cleaner import CleanedDocument, ContentBlock
from processor.metadata import build_chunk_metadata, make_chunk_id

try:
    import tiktoken

    _ENCODING = tiktoken.get_encoding("cl100k_base")
except Exception:  # noqa: BLE001 - allow char-based fallback without tiktoken
    _ENCODING = None


def count_tokens(text: str) -> int:
    if not text:
        return 0
    if _ENCODING is not None:
        return len(_ENCODING.encode(text))
    # Approximate GPT tokenization (~4 chars/token).
    return max(1, (len(text) + 3) // 4)


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    if count_tokens(text) <= max_tokens:
        return text
    if _ENCODING is not None:
        tokens = _ENCODING.encode(text)[:max_tokens]
        return _ENCODING.decode(tokens)
    return text[: max_tokens * 4]


def overlap_suffix(text: str, overlap_tokens: int) -> str:
    if overlap_tokens <= 0 or not text:
        return ""
    if _ENCODING is not None:
        tokens = _ENCODING.encode(text)
        if len(tokens) <= overlap_tokens:
            return text
        return _ENCODING.decode(tokens[-overlap_tokens:])
    return text[-(overlap_tokens * 4) :]


@dataclass(frozen=True)
class ChunkingConfig:
    chunk_size_tokens: int = 1000
    chunk_overlap_tokens: int = 150
    min_chunk_tokens: int = 40


def _group_blocks_by_section(blocks: Iterable[ContentBlock]) -> list[tuple[str, str, list[ContentBlock]]]:
    groups: list[tuple[str, str, list[ContentBlock]]] = []
    current_heading = ""
    current_section = ""
    current_blocks: list[ContentBlock] = []

    def flush() -> None:
        nonlocal current_blocks
        if current_blocks:
            groups.append((current_section, current_heading, current_blocks))
            current_blocks = []

    for block in blocks:
        if block.kind == "heading":
            flush()
            current_heading = block.heading or block.text.lstrip("# ").strip()
            current_section = block.section or current_heading
            current_blocks = [block]
            continue
        if not current_blocks and not current_heading:
            current_heading = ""
            current_section = ""
        current_blocks.append(block)

    flush()
    return groups


def _hard_split_by_tokens(text: str, config: ChunkingConfig) -> list[str]:
    """Split text by token windows with overlap. Guaranteed non-recursive."""
    if not text:
        return []
    if count_tokens(text) <= config.chunk_size_tokens:
        return [text]

    pieces: list[str] = []
    remaining = text
    guard = 0
    max_guard = max(8, count_tokens(text) // max(1, config.chunk_size_tokens - config.chunk_overlap_tokens) + 5)

    while remaining and guard < max_guard:
        guard += 1
        piece = truncate_to_tokens(remaining, config.chunk_size_tokens)
        if not piece:
            break
        pieces.append(piece)
        if piece == remaining:
            break

        if _ENCODING is not None:
            remaining_tokens = _ENCODING.encode(remaining)
            piece_tokens = _ENCODING.encode(piece)
            advance = max(1, len(piece_tokens) - config.chunk_overlap_tokens)
            if advance >= len(remaining_tokens):
                break
            remaining = _ENCODING.decode(remaining_tokens[advance:])
        else:
            overlap = overlap_suffix(piece, config.chunk_overlap_tokens)
            advance = max(1, len(piece) - len(overlap))
            if advance >= len(remaining):
                break
            remaining = remaining[advance:]

    if remaining and (not pieces or pieces[-1] != remaining):
        # Append any leftover that was not fully consumed.
        if pieces and count_tokens(remaining) < config.min_chunk_tokens:
            pieces[-1] = f"{pieces[-1]}\n\n{remaining}".strip()
        elif remaining not in pieces:
            pieces.append(remaining)
    return pieces


def _split_oversized_text(text: str, config: ChunkingConfig) -> list[str]:
    if count_tokens(text) <= config.chunk_size_tokens:
        return [text]

    units = [u.strip() for u in text.split("\n\n") if u.strip()]
    if len(units) == 1:
        units = [u.strip() for u in text.split("\n") if u.strip()]
    if len(units) == 1:
        return _hard_split_by_tokens(text, config)

    chunks: list[str] = []
    current = ""
    for unit in units:
        # Oversized atomic unit → hard split, then continue.
        if count_tokens(unit) > config.chunk_size_tokens:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_hard_split_by_tokens(unit, config))
            continue

        candidate = f"{current}\n\n{unit}".strip() if current else unit
        if count_tokens(candidate) <= config.chunk_size_tokens:
            current = candidate
            continue

        if current:
            chunks.append(current)
            overlap = overlap_suffix(current, config.chunk_overlap_tokens)
            current = f"{overlap}\n\n{unit}".strip() if overlap else unit
            if count_tokens(current) > config.chunk_size_tokens:
                chunks.extend(_hard_split_by_tokens(current, config))
                current = ""
        else:
            chunks.extend(_hard_split_by_tokens(unit, config))
            current = ""
    if current:
        chunks.append(current)
    return chunks


def chunk_document(
    document: CleanedDocument,
    *,
    source_type: str,
    config: ChunkingConfig | None = None,
) -> list[dict]:
    cfg = config or ChunkingConfig()
    if cfg.chunk_overlap_tokens >= cfg.chunk_size_tokens:
        raise ValueError("chunk_overlap_tokens must be smaller than chunk_size_tokens")

    groups = _group_blocks_by_section(document.blocks)
    if not groups and document.cleaned_text:
        groups = [("", document.page_title, [
            ContentBlock(
                kind="paragraph",
                text=document.cleaned_text,
                heading=document.page_title,
                section=document.page_title,
            )
        ])]

    chunks: list[dict] = []
    global_index = 0

    for section, heading, blocks in groups:
        section_text = "\n\n".join(block.text for block in blocks if block.text).strip()
        if not section_text:
            continue

        pieces = _split_oversized_text(section_text, cfg)
        for piece in pieces:
            token_count = count_tokens(piece)
            if token_count < cfg.min_chunk_tokens and chunks:
                # Merge tiny trailing fragments into previous chunk when possible.
                previous = chunks[-1]
                merged = f"{previous['text']}\n\n{piece}".strip()
                if count_tokens(merged) <= cfg.chunk_size_tokens + cfg.chunk_overlap_tokens:
                    previous["text"] = merged
                    previous["token_count"] = count_tokens(merged)
                    continue

            chunk_id = make_chunk_id(
                url=document.url,
                heading=heading or document.page_title,
                index=global_index,
                text=piece,
            )
            metadata = build_chunk_metadata(
                chunk_id=chunk_id,
                page_title=document.page_title,
                url=document.url,
                section=section or heading or document.page_title,
                heading=heading or document.page_title,
                crawl_timestamp=document.crawl_timestamp,
                source_type=source_type,
                extra={"token_count": token_count},
            )
            chunks.append(
                {
                    **metadata,
                    "text": piece,
                    "token_count": token_count,
                }
            )
            global_index += 1

    return chunks
