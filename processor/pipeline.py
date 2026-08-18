"""Orchestrate raw crawl → cleaned/chunked processed documents."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from crawler.hashing import generate_content_hash
from processor.chunker import ChunkingConfig, chunk_document
from processor.cleaner import clean_from_crawled_page
from processor.config import ProcessorSettings
from processor.metadata import slugify


@dataclass
class ProcessStats:
    input_pages: int = 0
    processed_pages: int = 0
    failed_pages: int = 0
    total_chunks: int = 0
    skipped_empty: int = 0


@dataclass
class ProcessResult:
    run_dir: Path
    stats: ProcessStats = field(default_factory=ProcessStats)
    failures: list[dict[str, Any]] = field(default_factory=list)


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def discover_page_files(raw_dir: Path, crawl_dir: Path | None = None) -> list[Path]:
    if crawl_dir is not None:
        pages_dir = crawl_dir / "pages"
        if not pages_dir.is_dir():
            raise FileNotFoundError(f"No pages directory in {crawl_dir}")
        return sorted(pages_dir.glob("*.json"))

    if not raw_dir.exists():
        return []

    crawl_runs = sorted(
        [p for p in raw_dir.glob("crawl_*") if p.is_dir()],
        key=lambda p: p.name,
        reverse=True,
    )
    if crawl_runs:
        return sorted((crawl_runs[0] / "pages").glob("*.json"))

    return sorted(raw_dir.glob("*.json"))


def _document_id(url: str, page_title: str) -> str:
    base = slugify(page_title or url, fallback="document")
    digest = slugify(url, fallback="page")[-12:]
    return f"{base}-{digest}"


def process_page_record(
    page: dict[str, Any],
    *,
    settings: ProcessorSettings,
) -> dict[str, Any]:
    cleaned = clean_from_crawled_page(page)
    chunks = chunk_document(
        cleaned,
        source_type=settings.source_type,
        config=ChunkingConfig(
            chunk_size_tokens=settings.chunk_size_tokens,
            chunk_overlap_tokens=settings.chunk_overlap_tokens,
            min_chunk_tokens=settings.min_chunk_tokens,
        ),
    )
    content_hash = str(page.get("content_hash") or generate_content_hash(cleaned.cleaned_text))
    for chunk in chunks:
        chunk["content_hash"] = content_hash
        chunk["source"] = "BMI Hub"
        chunk["access"] = str(page.get("access") or "authenticated")
        chunk["scraped_date"] = cleaned.crawl_timestamp
        chunk["document_id"] = _document_id(cleaned.url, cleaned.page_title)

    return {
        "document_id": _document_id(cleaned.url, cleaned.page_title),
        "url": cleaned.url,
        "page_title": cleaned.page_title,
        "crawl_timestamp": cleaned.crawl_timestamp,
        "source_type": settings.source_type,
        "cleaned_text": cleaned.cleaned_text,
        "preserved_links": cleaned.preserved_links,
        "sections": sorted(
            {
                block.section
                for block in cleaned.blocks
                if block.section
            }
        ),
        "chunk_count": len(chunks),
        "chunks": chunks,
        "content_hash": content_hash,
        "source": "BMI Hub",
        "access": str(page.get("access") or "authenticated"),
        "processing_timestamp": datetime.now(timezone.utc).isoformat(),
    }


class ContentProcessor:
    def __init__(self, settings: ProcessorSettings) -> None:
        self.settings = settings

    def run(self, *, crawl_dir: Path | None = None) -> ProcessResult:
        page_files = discover_page_files(self.settings.raw_dir, crawl_dir=crawl_dir)
        run_dir = self.settings.output_dir / f"process_{_utc_stamp()}"
        docs_dir = run_dir / "documents"
        docs_dir.mkdir(parents=True, exist_ok=True)

        result = ProcessResult(run_dir=run_dir)
        all_chunks: list[dict[str, Any]] = []

        for path in page_files:
            result.stats.input_pages += 1
            try:
                page = json.loads(path.read_text(encoding="utf-8"))
                processed = process_page_record(page, settings=self.settings)
                if not processed["cleaned_text"].strip() or not processed["chunks"]:
                    result.stats.skipped_empty += 1
                    continue

                out_name = path.stem + ".json"
                _write_json(docs_dir / out_name, processed)
                all_chunks.extend(processed["chunks"])
                result.stats.processed_pages += 1
                result.stats.total_chunks += len(processed["chunks"])
            except Exception as exc:  # noqa: BLE001 - continue processing remaining pages
                result.stats.failed_pages += 1
                result.failures.append(
                    {
                        "file": str(path),
                        "error": str(exc),
                    }
                )

        _write_jsonl(run_dir / "chunks.jsonl", all_chunks)
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "raw_dir": str(self.settings.raw_dir),
            "crawl_dir": str(crawl_dir) if crawl_dir else None,
            "output_dir": str(run_dir),
            "settings": {
                "chunk_size_tokens": self.settings.chunk_size_tokens,
                "chunk_overlap_tokens": self.settings.chunk_overlap_tokens,
                "min_chunk_tokens": self.settings.min_chunk_tokens,
                "source_type": self.settings.source_type,
            },
            "stats": asdict(result.stats),
            "failures": result.failures,
        }
        _write_json(run_dir / "process_report.json", report)
        print(
            "Processing complete: "
            f"{result.stats.processed_pages} pages, "
            f"{result.stats.total_chunks} chunks -> {run_dir}"
        )
        return result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Process crawled BMI Hub pages into cleaned RAG chunks."
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=None,
        help="Directory containing crawl_* runs (default: data/raw).",
    )
    parser.add_argument(
        "--crawl-dir",
        type=Path,
        default=None,
        help="Specific crawl run directory (e.g. data/raw/crawl_...).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Processed output root (default: data/processed).",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=None,
        help="Target chunk size in tokens (800-1200 recommended).",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=None,
        help="Chunk overlap in tokens (100-200 recommended).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    settings = ProcessorSettings.from_env()

    if args.raw_dir is not None:
        settings = replace(settings, raw_dir=args.raw_dir)
    if args.output_dir is not None:
        settings = replace(settings, output_dir=args.output_dir)
    if args.chunk_size is not None:
        settings = replace(settings, chunk_size_tokens=args.chunk_size)
    if args.chunk_overlap is not None:
        settings = replace(settings, chunk_overlap_tokens=args.chunk_overlap)

    if settings.chunk_size_tokens < 800 or settings.chunk_size_tokens > 1200:
        print(
            "Warning: chunk size outside recommended 800-1200 token range.",
            file=sys.stderr,
        )
    if settings.chunk_overlap_tokens < 100 or settings.chunk_overlap_tokens > 200:
        print(
            "Warning: chunk overlap outside recommended 100-200 token range.",
            file=sys.stderr,
        )

    processor = ContentProcessor(settings)
    result = processor.run(crawl_dir=args.crawl_dir)
    return 1 if result.stats.failed_pages and not result.stats.processed_pages else 0


if __name__ == "__main__":
    raise SystemExit(main())
