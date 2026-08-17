import json
from pathlib import Path

from crawler.embeddings import HashEmbeddingProvider
from crawler.indexer import (
    IndexerSettings,
    VectorIndexer,
    normalize_chunk_records,
)


def _write_process_run(root: Path) -> Path:
    run_dir = root / "process_test"
    run_dir.mkdir(parents=True, exist_ok=True)
    chunks = [
        {
            "chunk_id": "intro-0000-aaa111",
            "page_title": "Safety",
            "url": "https://bmihub.burnsmcd.com/safety",
            "section": "Intro",
            "heading": "Intro",
            "crawl_timestamp": "2026-01-01T00:00:00+00:00",
            "source_type": "bmi_hub_page",
            "token_count": 12,
            "text": "Wear PPE before entering the site.",
        },
        {
            "chunk_id": "limits-0001-bbb222",
            "page_title": "Safety",
            "url": "https://bmihub.burnsmcd.com/safety",
            "section": "Limits",
            "heading": "Limits",
            "crawl_timestamp": "2026-01-01T00:00:00+00:00",
            "source_type": "bmi_hub_page",
            "token_count": 10,
            "text": "Noise limit is 85 dB.",
        },
    ]
    with (run_dir / "chunks.jsonl").open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            handle.write(json.dumps(chunk) + "\n")
    return run_dir


def test_normalize_chunk_records_uses_stable_ids(tmp_path: Path) -> None:
    records = normalize_chunk_records(
        [
            {
                "chunk_id": "stable-id-1",
                "text": "hello",
                "page_title": "T",
                "url": "https://bmihub.burnsmcd.com/a",
                "section": "S",
                "heading": "H",
                "crawl_timestamp": "t",
                "source_type": "bmi_hub_page",
            },
            {
                "chunk_id": "stable-id-1",
                "text": "duplicate ignored",
                "page_title": "T",
                "url": "https://bmihub.burnsmcd.com/a",
            },
            {"chunk_id": "", "text": "missing id"},
        ]
    )
    assert len(records) == 1
    assert records[0]["id"] == "stable-id-1"
    assert records[0]["metadata"]["chunk_id"] == "stable-id-1"


def test_incremental_skips_existing_ids(tmp_path: Path) -> None:
    processed = tmp_path / "processed"
    chroma = tmp_path / "chroma"
    run_dir = _write_process_run(processed)

    settings = IndexerSettings(
        processed_dir=processed,
        chroma_persist_directory=chroma,
        collection_name="test_bmi_documents",
        batch_size=8,
    )
    indexer = VectorIndexer(
        settings=settings,
        embedding_provider=HashEmbeddingProvider(dimensions=16),
    )

    first = indexer.full_rebuild(process_dir=run_dir)
    assert first.upserted == 2
    assert first.collection_count == 2

    second = indexer.incremental_index(process_dir=run_dir)
    assert second.upserted == 0
    assert second.skipped_existing == 2
    assert second.collection_count == 2


def test_full_rebuild_replaces_collection(tmp_path: Path) -> None:
    processed = tmp_path / "processed"
    chroma = tmp_path / "chroma"
    run_dir = _write_process_run(processed)

    settings = IndexerSettings(
        processed_dir=processed,
        chroma_persist_directory=chroma,
        collection_name="test_bmi_rebuild",
        batch_size=8,
    )
    indexer = VectorIndexer(
        settings=settings,
        embedding_provider=HashEmbeddingProvider(dimensions=16),
    )

    indexer.full_rebuild(process_dir=run_dir)
    stats = indexer.statistics()
    assert stats["count"] == 2

    indexer.clear_index()
    assert indexer.statistics()["count"] == 0

    rebuilt = indexer.full_rebuild(process_dir=run_dir)
    assert rebuilt.upserted == 2
    assert rebuilt.collection_count == 2
