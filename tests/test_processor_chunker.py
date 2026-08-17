from processor.chunker import ChunkingConfig, chunk_document, count_tokens
from processor.cleaner import CleanedDocument, ContentBlock


def _long_paragraph(words: int = 900) -> str:
    return " ".join(f"word{i}" for i in range(words))


def test_chunking_respects_size_and_overlap_bounds() -> None:
    text = _long_paragraph(2500)
    document = CleanedDocument(
        url="https://bmihub.burnsmcd.com/long",
        page_title="Long Page",
        crawl_timestamp="2026-01-01T00:00:00+00:00",
        cleaned_text=text,
        blocks=[
            ContentBlock(kind="heading", text="# Long Page", heading="Long Page", section="Long Page", level=1),
            ContentBlock(kind="paragraph", text=text, heading="Long Page", section="Long Page"),
        ],
    )

    chunks = chunk_document(
        document,
        source_type="bmi_hub_page",
        config=ChunkingConfig(chunk_size_tokens=1000, chunk_overlap_tokens=150, min_chunk_tokens=40),
    )

    assert len(chunks) >= 2
    for chunk in chunks:
        assert chunk["token_count"] <= 1000 + 150


def test_chunking_keeps_section_context() -> None:
    document = CleanedDocument(
        url="https://bmihub.burnsmcd.com/sections",
        page_title="Sections",
        crawl_timestamp="2026-01-01T00:00:00+00:00",
        cleaned_text="alpha beta",
        blocks=[
            ContentBlock(kind="heading", text="# Intro", heading="Intro", section="Intro", level=1),
            ContentBlock(
                kind="paragraph",
                text=" ".join(["alpha"] * 200),
                heading="Intro",
                section="Intro",
            ),
            ContentBlock(kind="heading", text="## Details", heading="Details", section="Intro > Details", level=2),
            ContentBlock(
                kind="paragraph",
                text=" ".join(["beta"] * 200),
                heading="Details",
                section="Intro > Details",
            ),
        ],
    )

    chunks = chunk_document(
        document,
        source_type="bmi_hub_page",
        config=ChunkingConfig(chunk_size_tokens=900, chunk_overlap_tokens=120, min_chunk_tokens=10),
    )

    assert chunks
    assert any(chunk["heading"] == "Intro" for chunk in chunks)
    assert any(chunk["section"] == "Intro > Details" for chunk in chunks)
    assert all(count_tokens(chunk["text"]) == chunk["token_count"] for chunk in chunks)
