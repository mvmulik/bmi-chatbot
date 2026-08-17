from crawler.extractor import is_internal_url, normalize_url


def test_normalize_removes_fragment() -> None:
    assert (
        normalize_url("https://bmihub.burnsmcd.com/page#section")
        == "https://bmihub.burnsmcd.com/page"
    )


def test_normalize_resolves_relative() -> None:
    assert (
        normalize_url("/docs/a", "https://bmihub.burnsmcd.com/home")
        == "https://bmihub.burnsmcd.com/docs/a"
    )


def test_internal_host_only() -> None:
    assert is_internal_url("https://bmihub.burnsmcd.com/x")
    assert not is_internal_url("https://example.com/x")
