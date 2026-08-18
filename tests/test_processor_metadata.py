from processor.metadata import build_chunk_metadata, make_chunk_id
from processor.pipeline import process_page_record
from processor.config import ProcessorSettings


REQUIRED_KEYS = {
    "chunk_id",
    "page_title",
    "url",
    "section",
    "heading",
    "crawl_timestamp",
    "source_type",
    "source",
}


def test_build_chunk_metadata_contains_required_fields() -> None:
    metadata = build_chunk_metadata(
        chunk_id="intro-0001-abc",
        page_title="Safety Guide",
        url="https://bmihub.burnsmcd.com/safety",
        section="Safety Guide > Checklist",
        heading="Checklist",
        crawl_timestamp="2026-01-01T00:00:00+00:00",
        source_type="bmi_hub_page",
    )

    assert REQUIRED_KEYS.issubset(metadata.keys())
    assert metadata["source_type"] == "bmi_hub_page"


def test_make_chunk_id_is_stable_for_same_inputs() -> None:
    first = make_chunk_id(
        url="https://bmihub.burnsmcd.com/a",
        heading="Intro",
        index=0,
        text="hello world",
    )
    second = make_chunk_id(
        url="https://bmihub.burnsmcd.com/a",
        heading="Intro",
        index=0,
        text="hello world",
    )
    assert first == second
    assert first != make_chunk_id(
        url="https://bmihub.burnsmcd.com/a",
        heading="Intro",
        index=1,
        text="hello world",
    )


def test_process_page_record_attaches_metadata_to_chunks() -> None:
    page = {
        "url": "https://bmihub.burnsmcd.com/safety",
        "final_url": "https://bmihub.burnsmcd.com/safety",
        "page_title": "Safety Guide",
        "crawl_timestamp": "2026-01-01T00:00:00+00:00",
        "html": """
        <html><body><main>
          <h1>Safety Guide</h1>
          <p>""" + (" Important guidance." * 80) + """</p>
        </main></body></html>
        """,
    }

    processed = process_page_record(page, settings=ProcessorSettings())
    assert processed["chunks"]
    for chunk in processed["chunks"]:
        assert REQUIRED_KEYS.issubset(chunk.keys())
        assert chunk["url"] == "https://bmihub.burnsmcd.com/safety"
        assert chunk["page_title"] == "Safety Guide"
        assert chunk["source_type"] == "bmi_hub_page"
        assert chunk["source"] == "BMI Hub"
        assert "content_hash" in chunk
        assert "text" in chunk
