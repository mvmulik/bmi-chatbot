"""ChromaDB vector indexing for processed BMI Hub chunks."""

from __future__ import annotations

import argparse
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import chromadb
from chromadb.api.models.Collection import Collection
from dotenv import load_dotenv

from crawler.config import ROOT_DIR
from crawler.embeddings import EmbeddingProvider, create_embedding_provider

load_dotenv(ROOT_DIR / ".env")

logger = logging.getLogger(__name__)

METADATA_KEYS = (
    "chunk_id",
    "page_title",
    "url",
    "section",
    "heading",
    "crawl_timestamp",
    "source_type",
    "token_count",
    "document_id",
)


@dataclass(frozen=True)
class IndexerSettings:
    processed_dir: Path = ROOT_DIR / "data" / "processed"
    chroma_persist_directory: Path = ROOT_DIR / "data" / "chroma"
    collection_name: str = "bmi_documents"
    batch_size: int = 64

    @classmethod
    def from_env(cls) -> IndexerSettings:
        return cls(
            processed_dir=Path(
                os.getenv("INDEXER_PROCESSED_DIR", str(ROOT_DIR / "data" / "processed"))
            ),
            chroma_persist_directory=Path(
                os.getenv("CHROMA_PERSIST_DIRECTORY", str(ROOT_DIR / "data" / "chroma"))
            ),
            collection_name=os.getenv("CHROMA_COLLECTION_NAME", "bmi_documents").strip()
            or "bmi_documents",
            batch_size=int(os.getenv("INDEXER_BATCH_SIZE", os.getenv("EMBEDDING_BATCH_SIZE", "64"))),
        )


@dataclass
class IndexStats:
    total_chunks_loaded: int = 0
    upserted: int = 0
    skipped_existing: int = 0
    skipped_invalid: int = 0
    collection_count: int = 0
    mode: str = ""
    process_dir: str = ""
    embedding_model: str = ""
    collection_name: str = ""
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


def configure_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _newest_process_dir(processed_dir: Path) -> Path | None:
    if not processed_dir.exists():
        return None
    runs = sorted(
        [path for path in processed_dir.glob("process_*") if path.is_dir()],
        key=lambda path: path.name,
        reverse=True,
    )
    return runs[0] if runs else None


def _chroma_safe_metadata(raw: dict[str, Any]) -> dict[str, str | int | float | bool]:
    metadata: dict[str, str | int | float | bool] = {}
    for key in METADATA_KEYS:
        if key not in raw or raw[key] is None:
            continue
        value = raw[key]
        if isinstance(value, (str, int, float, bool)):
            metadata[key] = value
        else:
            metadata[key] = str(value)
    # Always keep stable identifiers as strings for consistency.
    if "chunk_id" in metadata:
        metadata["chunk_id"] = str(metadata["chunk_id"])
    return metadata


def load_processed_chunks(
    processed_dir: Path,
    *,
    process_dir: Path | None = None,
) -> tuple[Path, list[dict[str, Any]]]:
    """Load chunks from chunks.jsonl or documents/*.json under a process run."""
    run_dir = process_dir or _newest_process_dir(processed_dir)
    if run_dir is None:
        raise FileNotFoundError(
            f"No process_* directories found under {processed_dir}. Run the processor first."
        )

    chunks: list[dict[str, Any]] = []
    jsonl_path = run_dir / "chunks.jsonl"
    if jsonl_path.is_file():
        logger.info("Loading chunks from %s", jsonl_path)
        with jsonl_path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as exc:
                    logger.warning("Skipping invalid JSONL line %s: %s", line_number, exc)
                    continue
                if isinstance(payload, dict):
                    chunks.append(payload)
    else:
        docs_dir = run_dir / "documents"
        if not docs_dir.is_dir():
            raise FileNotFoundError(
                f"Neither chunks.jsonl nor documents/ found in {run_dir}"
            )
        logger.info("Loading chunks from documents in %s", docs_dir)
        for path in sorted(docs_dir.glob("*.json")):
            document = json.loads(path.read_text(encoding="utf-8"))
            document_id = document.get("document_id")
            for chunk in document.get("chunks") or []:
                if isinstance(chunk, dict):
                    if document_id and "document_id" not in chunk:
                        chunk = {**chunk, "document_id": document_id}
                    chunks.append(chunk)

    logger.info("Loaded %s chunks from %s", len(chunks), run_dir)
    return run_dir, chunks


def normalize_chunk_records(chunks: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate chunks and ensure stable IDs + metadata."""
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for chunk in chunks:
        chunk_id = str(chunk.get("chunk_id") or "").strip()
        text = str(chunk.get("text") or "").strip()
        if not chunk_id or not text:
            continue
        if chunk_id in seen_ids:
            logger.debug("Dropping duplicate chunk_id in input: %s", chunk_id)
            continue
        seen_ids.add(chunk_id)
        record = {
            "id": chunk_id,
            "text": text,
            "metadata": _chroma_safe_metadata(chunk),
        }
        # Ensure chunk_id is always present in metadata.
        record["metadata"]["chunk_id"] = chunk_id
        normalized.append(record)

    return normalized


class VectorIndexer:
    """Index processed chunks into a persistent ChromaDB collection."""

    def __init__(
        self,
        settings: IndexerSettings | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.settings = settings or IndexerSettings.from_env()
        self._embedder = embedding_provider
        self.settings.chroma_persist_directory.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=str(self.settings.chroma_persist_directory)
        )
        logger.info(
            "Chroma persistent client at %s (collection=%s)",
            self.settings.chroma_persist_directory,
            self.settings.collection_name,
        )

    @property
    def embedder(self) -> EmbeddingProvider:
        if self._embedder is None:
            self._embedder = create_embedding_provider()
        return self._embedder

    def _get_or_create_collection(self) -> Collection:
        metadata = {"hnsw:space": "cosine"}
        if self._embedder is not None:
            metadata["embedding_model"] = self.embedder.model_name
        return self._client.get_or_create_collection(
            name=self.settings.collection_name,
            metadata=metadata,
        )
    def _existing_ids(self, collection: Collection, ids: Sequence[str]) -> set[str]:
        existing: set[str] = set()
        batch_size = 500
        for start in range(0, len(ids), batch_size):
            batch = list(ids[start : start + batch_size])
            result = collection.get(ids=batch, include=[])
            existing.update(result.get("ids") or [])
        return existing

    def _upsert_records(
        self,
        collection: Collection,
        records: Sequence[dict[str, Any]],
    ) -> int:
        if not records:
            return 0

        upserted = 0
        batch_size = max(1, self.settings.batch_size)
        for start in range(0, len(records), batch_size):
            batch = list(records[start : start + batch_size])
            texts = [item["text"] for item in batch]
            ids = [item["id"] for item in batch]
            metadatas = [item["metadata"] for item in batch]
            logger.info(
                "Embedding/upserting batch %s-%s (%s records)",
                start + 1,
                start + len(batch),
                len(batch),
            )
            embeddings = self.embedder.embed_documents(texts)
            if len(embeddings) != len(batch):
                raise RuntimeError(
                    f"Embedding count mismatch: got {len(embeddings)} for {len(batch)} texts"
                )
            collection.upsert(
                ids=ids,
                documents=texts,
                metadatas=metadatas,
                embeddings=embeddings,
            )
            upserted += len(batch)
        return upserted

    def clear_index(self) -> IndexStats:
        logger.warning("Clearing Chroma collection '%s'", self.settings.collection_name)
        try:
            self._client.delete_collection(self.settings.collection_name)
            logger.info("Deleted collection '%s'", self.settings.collection_name)
        except Exception as exc:  # noqa: BLE001 - collection may not exist
            logger.info("Collection delete skipped/failed (%s); continuing.", exc)

        # Also remove orphaned files if the persist dir only holds this app's DB.
        # Keep directory itself so future writes succeed.
        persist = self.settings.chroma_persist_directory
        if persist.exists() and not any(persist.iterdir()):
            logger.debug("Chroma persist directory already empty: %s", persist)

        stats = IndexStats(
            mode="clear",
            collection_name=self.settings.collection_name,
            embedding_model=(
                self._embedder.model_name if self._embedder is not None else ""
            ),
            collection_count=0,
        )
        logger.info("Index cleared.")
        return stats

    def full_rebuild(
        self,
        *,
        process_dir: Path | None = None,
    ) -> IndexStats:
        logger.info("Starting full rebuild")
        self.clear_index()
        return self._index(mode="full", process_dir=process_dir, incremental=False)

    def incremental_index(
        self,
        *,
        process_dir: Path | None = None,
    ) -> IndexStats:
        logger.info("Starting incremental index")
        return self._index(mode="incremental", process_dir=process_dir, incremental=True)

    def _index(
        self,
        *,
        mode: str,
        process_dir: Path | None,
        incremental: bool,
    ) -> IndexStats:
        run_dir, raw_chunks = load_processed_chunks(
            self.settings.processed_dir,
            process_dir=process_dir,
        )
        valid_count_before = len(raw_chunks)
        records = normalize_chunk_records(raw_chunks)
        invalid = valid_count_before - len(records)
        skipped_existing = 0
        # Ensure collection metadata records the embedding model used.
        collection = self._get_or_create_collection()
        try:
            collection.modify(metadata={
                **(collection.metadata or {}),
                "hnsw:space": "cosine",
                "embedding_model": self.embedder.model_name,
            })
        except Exception as exc:  # noqa: BLE001
            logger.debug("Could not update collection metadata: %s", exc)

        if incremental and records:
            existing = self._existing_ids(collection, [item["id"] for item in records])
            before = len(records)
            records = [item for item in records if item["id"] not in existing]
            skipped_existing = before - len(records)
            logger.info(
                "Incremental mode: %s existing IDs skipped, %s new/changed to upsert",
                skipped_existing,
                len(records),
            )
        elif not incremental:
            # Full mode already cleared; upsert everything for idempotency.
            logger.info("Full mode: upserting %s records", len(records))

        upserted = self._upsert_records(collection, records)
        collection_count = collection.count()

        stats = IndexStats(
            total_chunks_loaded=len(raw_chunks),
            upserted=upserted,
            skipped_existing=skipped_existing,
            skipped_invalid=invalid,
            collection_count=collection_count,
            mode=mode,
            process_dir=str(run_dir),
            embedding_model=self.embedder.model_name,
            collection_name=self.settings.collection_name,
        )
        logger.info("Index complete: %s", asdict(stats))
        return stats

    def statistics(self) -> dict[str, Any]:
        collection = self._get_or_create_collection()
        count = collection.count()
        sample = collection.peek(limit=min(5, count)) if count else {"ids": [], "metadatas": []}
        collection_meta = collection.metadata or {}
        payload = {
            "collection_name": self.settings.collection_name,
            "persist_directory": str(self.settings.chroma_persist_directory),
            "count": count,
            "embedding_model": collection_meta.get(
                "embedding_model",
                self._embedder.model_name if self._embedder is not None else "",
            ),
            "sample_ids": sample.get("ids") or [],
            "sample_metadata": sample.get("metadatas") or [],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        logger.info("Index stats: count=%s collection=%s", count, self.settings.collection_name)
        return payload


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Index processed BMI Hub chunks into ChromaDB."
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    parser.add_argument(
        "--processed-dir",
        type=Path,
        default=None,
        help="Root processed directory (default: data/processed).",
    )
    parser.add_argument(
        "--process-dir",
        type=Path,
        default=None,
        help="Specific process_* directory to index.",
    )
    parser.add_argument(
        "--collection",
        type=str,
        default=None,
        help="Override Chroma collection name.",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("full", help="Clear the collection and re-index all chunks.")
    sub.add_parser(
        "incremental",
        help="Index only chunk IDs not already present in ChromaDB.",
    )
    sub.add_parser("clear", help="Delete the Chroma collection.")
    sub.add_parser("stats", help="Show index statistics.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    configure_logging(verbose=args.verbose)

    settings = IndexerSettings.from_env()
    if args.processed_dir is not None:
        settings = IndexerSettings(
            processed_dir=args.processed_dir,
            chroma_persist_directory=settings.chroma_persist_directory,
            collection_name=args.collection or settings.collection_name,
            batch_size=settings.batch_size,
        )
    elif args.collection:
        settings = IndexerSettings(
            processed_dir=settings.processed_dir,
            chroma_persist_directory=settings.chroma_persist_directory,
            collection_name=args.collection,
            batch_size=settings.batch_size,
        )

    try:
        indexer = VectorIndexer(settings=settings)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to initialize indexer: %s", exc)
        return 1

    try:
        if args.command == "full":
            stats = indexer.full_rebuild(process_dir=args.process_dir)
            print(json.dumps(asdict(stats), indent=2))
        elif args.command == "incremental":
            stats = indexer.incremental_index(process_dir=args.process_dir)
            print(json.dumps(asdict(stats), indent=2))
        elif args.command == "clear":
            stats = indexer.clear_index()
            print(json.dumps(asdict(stats), indent=2))
        elif args.command == "stats":
            print(json.dumps(indexer.statistics(), indent=2))
        else:
            parser.error(f"Unknown command: {args.command}")
            return 2
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        return 1
    except Exception as exc:  # noqa: BLE001
        logger.exception("Indexing command failed: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
