from crawler.discover import is_document_url, rank_records_for_query, rank_urls_for_query
from crawler.hashing import generate_content_hash
from crawler.state_store import STATUS_PROCESSED, CrawlRecord, CrawlStateStore


def test_content_hash_ignores_whitespace() -> None:
    first = generate_content_hash("Leave Policy\nEmployees are eligible")
    second = generate_content_hash("Leave Policy   Employees are eligible")
    assert first == second
    assert first != generate_content_hash("Different policy text")


def test_state_store_skips_unchanged_hash(tmp_path) -> None:  # noqa: ANN001
    store = CrawlStateStore(tmp_path / "crawl_state.json")
    url = "https://bmihub.burnsmcd.com/leave"
    digest = generate_content_hash("same")
    store.upsert(url, title="Leave", content_hash=digest, status=STATUS_PROCESSED)
    store.save()

    reloaded = CrawlStateStore(tmp_path / "crawl_state.json")
    assert reloaded.should_skip_unchanged(url, digest)
    assert not reloaded.should_skip_unchanged(url, generate_content_hash("changed"))


def test_rank_records_prefers_matching_titles() -> None:
    records = [
        CrawlRecord(url="https://bmihub.burnsmcd.com/it", title="Laptop requests"),
        CrawlRecord(url="https://bmihub.burnsmcd.com/hr/leave", title="Leave Policy"),
        CrawlRecord(url="https://example.com/leave", title="External leave"),
    ]
    ranked = rank_records_for_query(records, "How many leave days can I take?")
    assert ranked
    assert ranked[0].endswith("/hr/leave")


def test_document_url_detection() -> None:
    assert is_document_url("https://bmihub.burnsmcd.com/files/policy.pdf")
    assert not is_document_url("https://bmihub.burnsmcd.com/hr/leave")


def test_rank_urls_keeps_internal_only() -> None:
    urls = [
        "https://bmihub.burnsmcd.com/safety",
        "https://example.com/safety",
    ]
    ranked = rank_urls_for_query(urls, "safety guidance")
    assert ranked == ["https://bmihub.burnsmcd.com/safety"]
