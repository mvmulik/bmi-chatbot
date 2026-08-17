from processor.cleaner import clean_html


SAMPLE_HTML = """
<html>
  <head><title>BMI Sample Page</title></head>
  <body>
    <nav class="navbar">
      <a href="/home">Home</a>
      <a href="/guides">Guides</a>
    </nav>
    <header role="banner"><a href="/">BMI Hub</a></header>
    <main>
      <h1>Safety Guide</h1>
      <p>Welcome to the safety guide with <a href="https://bmihub.burnsmcd.com/docs/a">important docs</a>.</p>
      <h2>Checklist</h2>
      <ul>
        <li>Wear PPE</li>
        <li>Inspect tools</li>
      </ul>
      <h2>Limits</h2>
      <table>
        <tr><th>Item</th><th>Limit</th></tr>
        <tr><td>Noise</td><td>85 dB</td></tr>
      </table>
      <p>Follow local procedures at all times.</p>
    </main>
    <footer>
      <p>Copyright 2026 Burns &amp; McDonnell. All rights reserved.</p>
      <p>Privacy Policy</p>
    </footer>
    <script>alert('x')</script>
  </body>
</html>
"""


def test_clean_html_removes_nav_footer_and_scripts() -> None:
    cleaned = clean_html(
        SAMPLE_HTML,
        url="https://bmihub.burnsmcd.com/safety",
        page_title="BMI Sample Page",
        crawl_timestamp="2026-01-01T00:00:00+00:00",
    )

    assert "Wear PPE" in cleaned.cleaned_text
    assert "Copyright 2026" not in cleaned.cleaned_text
    assert "alert(" not in cleaned.cleaned_text
    assert "Privacy Policy" not in cleaned.cleaned_text
    # Navigation labels should not dominate cleaned body text.
    assert "Guides" not in cleaned.cleaned_text


def test_clean_html_preserves_headings_lists_tables_links() -> None:
    cleaned = clean_html(
        SAMPLE_HTML,
        url="https://bmihub.burnsmcd.com/safety",
        page_title="BMI Sample Page",
    )

    assert "# Safety Guide" in cleaned.cleaned_text
    assert "## Checklist" in cleaned.cleaned_text
    assert "- Wear PPE" in cleaned.cleaned_text
    assert "Noise | 85 dB" in cleaned.cleaned_text
    assert "[important docs](https://bmihub.burnsmcd.com/docs/a)" in cleaned.cleaned_text
    assert any(block.kind == "list" for block in cleaned.blocks)
    assert any(block.kind == "table" for block in cleaned.blocks)
