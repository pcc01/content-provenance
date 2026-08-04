"""
Tests for the site audit API (Phase 11): a real headless-browser crawl of a
local static multi-page fixture site with an intentional issue baked in for
each check (mixed-locale mismatch, RTL-risk CSS, an i18n-library signature,
a leaked ICU MessageFormat string, and a privacy-policy language mismatch).
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
</style>
</head>
<body>
  <h1>Welcome to our fixture website for automated testing</h1>
  <p>This paragraph exists purely so the crawler has enough English text to detect confidently as English content for the audit test suite.</p>
  <p>You have {count, plural, one {# new message} other {# new messages}} waiting for you today.</p>
  <a href="/fr/page.html">Francais version</a>
  <a href="/privacy.html">Privacy Policy</a>
  <script>
    // pretend i18next is in use here
    var i18n = window.i18next && window.i18next.init({ lng: 'en' });
  </script>
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
    assert audit["pages_crawled"] == 3
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

    mismatch = next(f for f in findings if f["finding_type"] == "page_language_mismatch")
    assert mismatch["detail"]["expected"] == "fr"
    assert mismatch["detail"]["detected"] == "en"

    privacy_mismatch = next(f for f in findings if f["finding_type"] == "privacy_language_mismatch")
    assert privacy_mismatch["detail"]["from_lang"] == "en"
    assert privacy_mismatch["detail"]["privacy_lang"] == "fr"


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
    assert len(pages) == 3
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
