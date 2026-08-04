"""
Tests for the site audit API (Phase 11/12): a real headless-browser crawl of
a local static multi-page fixture site with an intentional issue baked in
for each check (mixed-locale mismatch, RTL-risk CSS, an i18n-library
signature, a leaked ICU MessageFormat string, a privacy-policy language
mismatch, a text-expansion-risk CSS rule, a leaked template placeholder, a
missing GDPR-style cookie-consent mechanism, US-centric form assumptions on
a German-targeted page, a missing Arabic-covering font, and a missing
hreflang annotation on a multi-locale site).
Run with: PYTHONPATH=. pytest tests/test_audit.py -v
"""

import functools
import http.server
import tempfile
import threading
from pathlib import Path

import pytest

_INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head><title>Fixture Home</title>
<style>
  .card { margin-left: 12px; margin-right: 8px; }
  .card2 { padding-left: 4px; padding-right: 4px; }
  .aside { float: right; }
  .label { text-align: left; }
  .banner { border-left: 2px solid red; }
  .btn1 { width: 100px; overflow: hidden; }
  .btn2 { width: 120px; overflow: hidden; }
</style>
</head>
<body>
  <h1>Welcome to our fixture website for automated testing</h1>
  <p>This paragraph exists purely so the crawler has enough English text to detect confidently as English content for the audit test suite.</p>
  <p>You have {count, plural, one {# new message} other {# new messages}} waiting for you today.</p>
  <p>Hello {{ userName }}, welcome back to your dashboard today.</p>
  <a href="/fr/page.html">Francais version</a>
  <a href="/de-de/page.html">Deutsche Version</a>
  <a href="/ar-sa/page.html">Arabic version</a>
  <a href="/privacy.html">Privacy Policy</a>
  <script>
    // pretend i18next is in use here
    var i18n = window.i18next && window.i18next.init({ lng: 'en' });
  </script>
</body>
</html>
"""

# German-locale page (via URL path region subtag /de-de/) with a US-centric
# form (5-digit zip, US phone pattern, US-state dropdown) and no cookie-
# consent mechanism — GDPR (via region DE) requires one.
_DE_PAGE_HTML = """<!DOCTYPE html>
<html lang="de-DE">
<head><title>Deutsche Seite</title></head>
<body>
  <h1>Willkommen auf unserer deutschen Seite fuer diesen automatisierten Test</h1>
  <p>Dieser Absatz enthaelt genuegend deutschen Text, damit die Spracherkennung ihn zuverlaessig als Deutsch erkennt.</p>
  <form>
    <input name="zip" pattern="[0-9]{5}" maxlength="5">
    <input name="phone" pattern="\\d{3}-\\d{3}-\\d{4}">
    <select name="state">
      <option>AL</option><option>AK</option><option>AZ</option><option>AR</option><option>CA</option>
      <option>CO</option><option>CT</option><option>DE</option><option>FL</option><option>GA</option>
      <option>HI</option><option>ID</option><option>IL</option><option>IN</option><option>IA</option>
      <option>KS</option><option>KY</option><option>LA</option><option>ME</option>
    </select>
  </form>
</body>
</html>
"""

# Arabic-locale page (via URL path region subtag /ar-sa/) with no
# Arabic-covering font declared anywhere in its CSS.
_AR_PAGE_HTML = """<!DOCTYPE html>
<html lang="ar-SA">
<head><title>Arabic Fixture Page</title>
<style>.text { font-family: Helvetica, Arial, sans-serif; }</style>
</head>
<body>
  <h1>This page targets an Arabic-speaking market but declares no Arabic-covering font</h1>
  <p>This paragraph exists purely so the crawler has enough English text to detect confidently as English content for the audit test suite here.</p>
</body>
</html>
"""

# Lives at /fr/page.html (URL suggests French) but the content is plain
# English — this is the page_language_mismatch fixture.
_FR_PATH_ENGLISH_CONTENT_HTML = """<!DOCTYPE html>
<html lang="en">
<head><title>Mislabeled Page</title></head>
<body>
  <h1>This page pretends to be French but is written entirely in English</h1>
  <p>Despite living under a French locale path, every sentence on this page is in plain English for testing purposes.</p>
</body>
</html>
"""

# Genuinely French privacy content, linked from the (English) home page —
# this is the privacy_language_mismatch fixture.
_PRIVACY_FRENCH_HTML = """<!DOCTYPE html>
<html lang="fr">
<head><title>Politique de confidentialite</title></head>
<body>
  <h1>Politique de confidentialite</h1>
  <p>Cette politique de confidentialite decrit comment nous collectons, utilisons et protegeons vos informations personnelles conformement aux lois applicables en matiere de protection des donnees.</p>
</body>
</html>
"""


@pytest.fixture(scope="module")
def audit_fixture_server():
    tmpdir = tempfile.mkdtemp()
    (Path(tmpdir) / "index.html").write_text(_INDEX_HTML, encoding="utf-8")
    (Path(tmpdir) / "privacy.html").write_text(_PRIVACY_FRENCH_HTML, encoding="utf-8")
    fr_dir = Path(tmpdir) / "fr"
    fr_dir.mkdir()
    (fr_dir / "page.html").write_text(_FR_PATH_ENGLISH_CONTENT_HTML, encoding="utf-8")
    de_dir = Path(tmpdir) / "de-de"
    de_dir.mkdir()
    (de_dir / "page.html").write_text(_DE_PAGE_HTML, encoding="utf-8")
    ar_dir = Path(tmpdir) / "ar-sa"
    ar_dir.mkdir()
    (ar_dir / "page.html").write_text(_AR_PAGE_HTML, encoding="utf-8")

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=tmpdir)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    yield f"{base_url}/index.html"
    server.shutdown()


@pytest.mark.asyncio
async def test_audit_run_finds_every_seeded_issue(client, audit_fixture_server):
    r = await client.post("/api/v1/audit/runs", json={
        "root_url": audit_fixture_server, "primary_language": "en", "max_pages": 10,
    })
    assert r.status_code == 200
    audit = r.json()
    assert audit["status"] == "completed"
    assert audit["pages_crawled"] == 5
    audit_id = audit["id"]

    findings_r = await client.get(f"/api/v1/audit/runs/{audit_id}/findings")
    assert findings_r.status_code == 200
    findings = findings_r.json()
    types_found = {f["finding_type"] for f in findings}

    assert "page_language_mismatch" in types_found
    assert "rtl_risk_physical_properties" in types_found
    assert "icu_library_detected" in types_found
    assert "icu_syntax_leak" in types_found
    assert "privacy_link_found" in types_found
    assert "privacy_language_mismatch" in types_found
    assert "text_expansion_risk" in types_found
    assert "placeholder_leak" in types_found
    assert "missing_cookie_consent_mechanism" in types_found
    assert "possible_missing_script_font" in types_found
    assert "missing_hreflang_annotations" in types_found
    assert types_found & {"us_centric_postal_code_field", "us_centric_phone_format", "us_state_dropdown_on_non_us_page"}

    mismatch = next(f for f in findings if f["finding_type"] == "page_language_mismatch")
    assert mismatch["detail"]["expected"] == "fr"
    assert mismatch["detail"]["detected"] == "en"

    privacy_mismatch = next(f for f in findings if f["finding_type"] == "privacy_language_mismatch")
    assert privacy_mismatch["detail"]["from_lang"] == "en"
    assert privacy_mismatch["detail"]["privacy_lang"] == "fr"

    cookie_finding = next(f for f in findings if f["finding_type"] == "missing_cookie_consent_mechanism")
    assert cookie_finding["detail"]["region"] == "DE"

    font_finding = next(f for f in findings if f["finding_type"] == "possible_missing_script_font")
    assert font_finding["detail"]["script"] == "Arabic"


@pytest.mark.asyncio
async def test_audit_run_summary_and_pages(client, audit_fixture_server):
    r = await client.post("/api/v1/audit/runs", json={
        "root_url": audit_fixture_server, "primary_language": "en", "max_pages": 10,
    })
    audit_id = r.json()["id"]

    summary_r = await client.get(f"/api/v1/audit/runs/{audit_id}")
    assert summary_r.status_code == 200
    summary = summary_r.json()
    assert summary["audit"]["id"] == audit_id
    assert sum(summary["findings_by_check"].values()) > 0

    pages_r = await client.get(f"/api/v1/audit/runs/{audit_id}/pages")
    assert pages_r.status_code == 200
    pages = pages_r.json()
    assert len(pages) == 5
    urls = {p["url"] for p in pages}
    assert audit_fixture_server in urls


@pytest.mark.asyncio
async def test_audit_findings_filterable_by_check(client, audit_fixture_server):
    r = await client.post("/api/v1/audit/runs", json={
        "root_url": audit_fixture_server, "primary_language": "en", "max_pages": 10,
        "checks": ["mixed_locale"],
    })
    audit_id = r.json()["id"]

    findings_r = await client.get(f"/api/v1/audit/runs/{audit_id}/findings")
    findings = findings_r.json()
    assert findings  # mixed_locale alone still produces the language-mismatch finding
    assert all(f["check"] == "mixed_locale" for f in findings)


@pytest.mark.asyncio
async def test_audit_export_report(client, audit_fixture_server):
    r = await client.post("/api/v1/audit/runs", json={
        "root_url": audit_fixture_server, "primary_language": "en", "max_pages": 10,
    })
    audit_id = r.json()["id"]

    export_r = await client.get(f"/api/v1/audit/runs/{audit_id}/export")
    assert export_r.status_code == 200
    assert "Site I18n & Compliance Audit Report" in export_r.text
    assert audit_fixture_server in export_r.text


@pytest.mark.asyncio
async def test_audit_pdf_report(client, audit_fixture_server):
    r = await client.post("/api/v1/audit/runs", json={
        "root_url": audit_fixture_server, "primary_language": "en", "max_pages": 10,
    })
    audit_id = r.json()["id"]

    pdf_r = await client.get(f"/api/v1/audit/runs/{audit_id}/report.pdf")
    assert pdf_r.status_code == 200
    assert pdf_r.headers["content-type"] == "application/pdf"
    assert pdf_r.content[:4] == b"%PDF"
    assert len(pdf_r.content) > 1000


@pytest.mark.asyncio
async def test_audit_run_404_for_unknown_id(client):
    r = await client.get("/api/v1/audit/runs/does-not-exist")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_audit_run_rejects_non_http_scheme(client):
    r = await client.post("/api/v1/audit/runs", json={
        "root_url": "file:///etc/passwd", "primary_language": "en",
    })
    assert r.status_code == 200  # runs synchronously and reports failure in the body, not an HTTP error
    audit = r.json()
    assert audit["status"] == "failed"
    assert audit["error"]
