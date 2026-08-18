from crawler.auth_signals import (
    looks_like_access_denied,
    looks_like_login_url,
    looks_like_sign_in_title,
    parse_auth_selectors,
)
from crawler.extractor import extract_page_content, is_allowed_url, is_internal_url, normalize_url
from crawler.logutil import log_path, redact


def test_allowed_url_requires_https_hub_host() -> None:
    assert is_allowed_url("https://bmihub.burnsmcd.com/hr/leave")
    assert not is_allowed_url("http://bmihub.burnsmcd.com/hr/leave")
    assert not is_allowed_url("https://example.com/hr/leave")
    assert is_internal_url("https://bmihub.burnsmcd.com/x")


def test_login_url_detection() -> None:
    allowed = frozenset({"bmihub.burnsmcd.com"})
    assert looks_like_login_url(
        "https://login.microsoftonline.com/common/oauth2/authorize",
        allowed,
    )
    assert looks_like_login_url(
        "https://bmihub.burnsmcd.com/_layouts/15/Authenticate.aspx",
        allowed,
    )
    assert not looks_like_login_url("https://bmihub.burnsmcd.com/hr/leave-policy", allowed)
    assert looks_like_sign_in_title("Sign in to your account")
    assert not looks_like_sign_in_title("BMI Hub")


def test_access_denied_detection() -> None:
    assert looks_like_access_denied(
        status=403,
        page_url="https://bmihub.burnsmcd.com/restricted",
        title="Forbidden",
        html_excerpt="<html></html>",
    )
    assert looks_like_access_denied(
        status=200,
        page_url="https://bmihub.burnsmcd.com/restricted",
        title="Access Denied",
        html_excerpt="You don't have access to this page",
    )
    assert not looks_like_access_denied(
        status=200,
        page_url="https://bmihub.burnsmcd.com/hr/leave",
        title="Leave Policy",
        html_excerpt="<p>Employees are eligible</p>",
    )


def test_redact_and_log_path_hide_secrets() -> None:
    assert "***" in redact("Authorization: Bearer abc.def")
    assert "secret-cookie" not in redact("Cookie: secret-cookie")
    assert log_path("https://bmihub.burnsmcd.com/hr/leave?token=abc") == "/hr/leave"


def test_extract_records_authenticated_access() -> None:
    page = extract_page_content(
        url="https://bmihub.burnsmcd.com/hr/leave",
        final_url="https://bmihub.burnsmcd.com/hr/leave",
        html="<html><head><title>BMI Hub Leave Policy</title></head><body><p>Eligible employees</p></body></html>",
        status_code=200,
    )
    assert page["source"] == "BMI Hub"
    assert page["access"] == "authenticated"
    assert page["content"]
    assert page["scraped_at"]
    assert normalize_url(page["url"]) == "https://bmihub.burnsmcd.com/hr/leave"


def test_default_auth_selectors_are_non_empty() -> None:
    selectors = parse_auth_selectors("")
    assert "#O365_MainLink_Me" in selectors
    assert parse_auth_selectors("#myProfile, #logout") == ("#myProfile", "#logout")
