"""
Tests for the pages API (Phase 8): fetch + rewrite review for arbitrary
URLs — a real headless-browser render against a local static fixture
server, so these are slower than the rest of the suite by nature.
Run with: PYTHONPATH=. pytest tests/test_pages.py -v
"""

import functools
import http.server
import re
import tempfile
import threading
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.core.database import get_db

_FIXTURE_HTML = """<!DOCTYPE html>
<html>
<head><title>Fixture Page</title></head>
<body>
  <h1>Welcome to the fixture</h1>
  <p>This is a paragraph for harvesting.</p>
  <button>Click me</button>
  <button>Click me</button>
  <img src="/logo.png" alt="logo">
</body>
</html>
"""


@pytest.fixture(scope="module")
def fixture_server():
    tmpdir = tempfile.mkdtemp()
    (Path(tmpdir) / "index.html").write_text(_FIXTURE_HTML, encoding="utf-8")
    (Path(tmpdir) / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=tmpdir)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    yield f"{base_url}/index.html"
    server.shutdown()


@pytest.mark.asyncio
async def test_render_page_harvests_tags_and_rewrites_urls(client, fixture_server):
    r = await client.get(
        "/api/v1/pages/render", params={"url": fixture_server, "target_language": "fr-FR"},
    )
    assert r.status_code == 200
    html = r.text

    assert 'data-tu-id="' in html
    assert "[FR] Welcome to the fixture" in html
    assert "[FR] This is a paragraph for harvesting." in html
    assert 'src="/sdk-dist/overlay.js"' in html or "ReviewSDK" in html

    # The two identical "Click me" buttons must get distinct ids — dom_path
    # (including nth-of-type) disambiguates them, not just their text.
    assert html.count("[FR] Click me") == 2
    tu_id_count = html.count("data-tu-id=")
    assert tu_id_count == 4  # h1, p, and both buttons

    # img src was rewritten from a relative path to this fixture server's
    # own absolute origin, not left relative (which would 404 once served
    # from content-provenance's own origin).
    assert f'src="{fixture_server.rsplit("/", 1)[0]}/logo.png"' in html


@pytest.mark.asyncio
async def test_render_page_reuses_units_on_refetch(client, fixture_server):
    first = await client.get(
        "/api/v1/pages/render",
        params={"url": fixture_server, "target_language": "de-DE", "refresh": "true"},
    )
    second = await client.get(
        "/api/v1/pages/render",
        params={"url": fixture_server, "target_language": "de-DE", "refresh": "true"},
    )
    assert first.status_code == second.status_code == 200

    def tu_ids(html: str) -> set[str]:
        import re
        return set(re.findall(r'data-tu-id="([^"]+)"', html))

    first_ids, second_ids = tu_ids(first.text), tu_ids(second.text)
    assert len(first_ids) == 4
    assert first_ids == second_ids  # same content -> same matched units, no duplicates


@pytest.mark.asyncio
async def test_render_page_caches_by_default(client, fixture_server):
    db = get_db()

    await client.get("/api/v1/pages/render", params={"url": fixture_server, "target_language": "ja-JP"})
    await client.get("/api/v1/pages/render", params={"url": fixture_server, "target_language": "ja-JP"})

    snapshots = await db.list_page_snapshots(fixture_server, "ja-JP")
    assert len(snapshots) == 1  # second call served from cache, no new fetch


@pytest.mark.asyncio
async def test_render_page_rejects_non_http_scheme(client):
    r = await client.get(
        "/api/v1/pages/render", params={"url": "file:///etc/passwd", "target_language": "fr-FR"},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_page_history_as_of_and_diff(client, fixture_server):
    db = get_db()

    first = await client.get(
        "/api/v1/pages/render",
        params={"url": fixture_server, "target_language": "it-IT", "refresh": "true"},
    )
    assert first.status_code == 200
    ids = re.findall(r'data-tu-id="([^"]+)"', first.text)
    assert len(ids) == 4
    edited_unit_id = ids[0]  # the "Welcome to the fixture" heading

    original_unit = await db.get_translation_unit(edited_unit_id)
    original_text = original_unit.target_text

    initial_timestamps = await db.list_version_timestamps(ids)
    assert len(initial_timestamps) == 1
    t0 = initial_timestamps[0]

    # A later edit to just this one segment, with a controlled timestamp so
    # the as_of/diff assertions below are deterministic.
    t1 = t0 + timedelta(seconds=10)
    edited_unit = await db.get_translation_unit(edited_unit_id)
    edited_unit.target_text = "[IT] Manually edited heading"
    edited_unit.translated_at = t1
    await db.save_translation_unit(edited_unit, version_source_event="human_edit", version_note="test edit")

    history_r = await client.get(
        "/api/v1/pages/history", params={"url": fixture_server, "target_language": "it-IT"},
    )
    assert history_r.status_code == 200
    assert len(history_r.json()["timestamps"]) == 2

    as_of_before = await client.get(
        "/api/v1/pages/render",
        params={"url": fixture_server, "target_language": "it-IT", "as_of": t0.isoformat()},
    )
    assert as_of_before.status_code == 200
    assert original_text in as_of_before.text
    assert "Manually edited heading" not in as_of_before.text

    as_of_after = await client.get(
        "/api/v1/pages/render",
        params={"url": fixture_server, "target_language": "it-IT", "as_of": t1.isoformat()},
    )
    assert as_of_after.status_code == 200
    assert "Manually edited heading" in as_of_after.text

    diff_r = await client.get(
        "/api/v1/pages/diff",
        params={
            "url": fixture_server, "target_language": "it-IT",
            "from_ts": t0.isoformat(), "to_ts": t1.isoformat(),
        },
    )
    assert diff_r.status_code == 200
    changes = diff_r.json()["changes"]
    assert len(changes) == 1
    assert changes[0]["unit_id"] == edited_unit_id
    assert changes[0]["before_text"] == original_text
    assert changes[0]["after_text"] == "[IT] Manually edited heading"


@pytest.mark.asyncio
async def test_page_render_as_of_accepts_tz_aware_timestamp(client, fixture_server):
    """Regression: `new Date().toISOString()` on the frontend (e.g.
    PendingChanges' onApplied refresh) produces a "Z"-suffixed, tz-aware
    timestamp. Every created_at/fetched_at in this system is stored as a
    naive datetime.utcnow(), so comparing against a tz-aware `as_of` used to
    raise TypeError ("can't compare offset-naive and offset-aware
    datetimes"), 500ing the render endpoint — see _naive_utc in
    app/api/pages.py."""
    r = await client.get(
        "/api/v1/pages/render",
        params={"url": fixture_server, "target_language": "sv-SE", "refresh": "true"},
    )
    assert r.status_code == 200

    aware_as_of = datetime.utcnow().isoformat() + "Z"
    as_of_r = await client.get(
        "/api/v1/pages/render",
        params={"url": fixture_server, "target_language": "sv-SE", "as_of": aware_as_of},
    )
    assert as_of_r.status_code == 200


@pytest.mark.asyncio
async def test_page_diff_accepts_tz_aware_timestamps(client, fixture_server):
    r = await client.get(
        "/api/v1/pages/render",
        params={"url": fixture_server, "target_language": "nb-NO", "refresh": "true"},
    )
    assert r.status_code == 200

    aware_from = (datetime.utcnow() - timedelta(minutes=1)).isoformat() + "Z"
    aware_to = datetime.utcnow().isoformat() + "Z"
    diff_r = await client.get(
        "/api/v1/pages/diff",
        params={"url": fixture_server, "target_language": "nb-NO", "from_ts": aware_from, "to_ts": aware_to},
    )
    assert diff_r.status_code == 200


@pytest.mark.asyncio
async def test_redrive_approve_without_advancing_translated_at_still_shows_in_as_of(client, fixture_server):
    """Regression: the real approve_item()/_apply_redrive() code path never
    updates unit.translated_at (only unit-creation call sites do). Before
    the fix, save_translation_unit stamped EVERY version's created_at from
    unit.translated_at, so a redrive's new version got the exact same
    created_at as the original — ties in _version_as_of's max() then
    silently kept the OLD text in as_of/diff reconstruction even though the
    live unit.target_text (and the UI's segment list) had the new text.
    Exercises the actual propose -> approve flow, not a manually-advanced
    timestamp, so it fails the way the live bug did."""
    db = get_db()

    first = await client.get(
        "/api/v1/pages/render",
        params={"url": fixture_server, "target_language": "fi-FI", "refresh": "true"},
    )
    assert first.status_code == 200
    ids = re.findall(r'data-tu-id="([^"]+)"', first.text)
    unit_id = ids[0]

    propose_r = await client.post(
        "/api/v1/redrive/propose",
        json={"unit_id": unit_id, "proposed_text": "[FI] Approved via test", "proposed_by": "reviewer@example.com"},
    )
    assert propose_r.status_code == 201
    item = propose_r.json()

    approve_r = await client.post(
        f"/api/v1/redrive/runs/{item['run_id']}/items/{item['id']}/approve",
        json={"actor": "editor@example.com"},
    )
    assert approve_r.status_code == 200

    versions = await db.list_translation_unit_versions(unit_id)
    assert len(versions) == 2
    assert versions[1].created_at > versions[0].created_at

    as_of_after = await client.get(
        "/api/v1/pages/render",
        params={
            "url": fixture_server, "target_language": "fi-FI",
            "as_of": datetime.utcnow().isoformat(),
        },
    )
    assert as_of_after.status_code == 200
    assert "Approved via test" in as_of_after.text


@pytest.mark.asyncio
async def test_page_history_404s_for_unknown_page(client):
    r = await client.get(
        "/api/v1/pages/history",
        params={"url": "http://example.invalid/never-fetched", "target_language": "fr-FR"},
    )
    assert r.status_code == 404


# ── Phase 10 ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_harvest_endpoint_matches_units_without_playwright(client):
    """The extension's content script already walked the DOM itself (a
    real live tab, not a headless-browser fetch) — /pages/harvest only
    does the matching/translation step. No fixture_server needed here,
    just a hand-built items list."""
    url = "https://example.org/extension-test-page"
    body = {
        "url": url,
        "target_language": "fr-FR",
        "source_language": "en-US",
        "method": "ai",
        "items": [
            {"idx": 0, "domPath": "BODY>H1", "text": "Live Heading"},
            {"idx": 1, "domPath": "BODY>P", "text": "Live paragraph text."},
        ],
    }
    r = await client.post("/api/v1/pages/harvest", json=body)
    assert r.status_code == 200
    mapping = r.json()["mapping"]
    assert len(mapping) == 2
    assert mapping["0"]["targetText"] == "[FR] Live Heading"
    assert mapping["1"]["targetText"] == "[FR] Live paragraph text."

    # Re-harvesting the same page (a second "visit" to the live tab) reuses
    # the same units — no duplicates, matching Phase 8's fetch behavior.
    r2 = await client.post("/api/v1/pages/harvest", json=body)
    mapping2 = r2.json()["mapping"]
    assert mapping["0"]["tuId"] == mapping2["0"]["tuId"]
    assert mapping["1"]["tuId"] == mapping2["1"]["tuId"]


@pytest.mark.asyncio
async def test_page_notes_crud(client):
    url = "https://example.org/notes-test-page"
    create_r = await client.post(
        "/api/v1/pages/notes",
        json={"url": url, "target_language": "fr-FR", "author": "reviewer@example.com", "body": "Use formal register throughout."},
    )
    assert create_r.status_code == 201
    note = create_r.json()
    assert note["page_url"] == url
    assert note["unit_id"] is None

    list_r = await client.get("/api/v1/pages/notes", params={"url": url, "target_language": "fr-FR"})
    assert list_r.status_code == 200
    notes = list_r.json()
    assert len(notes) == 1
    assert notes[0]["body"] == "Use formal register throughout."

    resolve_r = await client.put(f"/api/v1/pages/notes/{note['id']}/resolve", params={"resolved": "true"})
    assert resolve_r.status_code == 200
    assert resolve_r.json()["resolved"] is True


@pytest.mark.asyncio
async def test_page_notes_do_not_leak_into_unrelated_pages(client):
    await client.post(
        "/api/v1/pages/notes",
        json={"url": "https://a.example.org/", "target_language": "fr-FR", "author": "x", "body": "note on A"},
    )
    list_r = await client.get(
        "/api/v1/pages/notes", params={"url": "https://b.example.org/", "target_language": "fr-FR"},
    )
    assert list_r.json() == []
