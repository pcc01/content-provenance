"""
Tests for Phase 10's editor view backend: listing pending proposals for a
page and bulk-approving them, plus the has_pending_proposal flag the
review overlay uses for in-page highlighting.
Run with: PYTHONPATH=. pytest tests/test_pending_changes.py -v
"""

import functools
import http.server
import tempfile
import threading
from pathlib import Path

import pytest

_FIXTURE_HTML = """<!DOCTYPE html>
<html>
<head><title>Pending Changes Fixture</title></head>
<body>
  <h1>Pending Fixture Heading</h1>
  <p>Pending fixture paragraph.</p>
</body>
</html>
"""


@pytest.fixture(scope="module")
def pending_fixture_server():
    tmpdir = tempfile.mkdtemp()
    (Path(tmpdir) / "index.html").write_text(_FIXTURE_HTML, encoding="utf-8")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=tmpdir)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/index.html"
    server.shutdown()


@pytest.mark.asyncio
async def test_pending_and_bulk_approve_flow(client, pending_fixture_server):
    render_r = await client.get(
        "/api/v1/pages/render",
        params={"url": pending_fixture_server, "target_language": "es-ES", "refresh": "true"},
    )
    assert render_r.status_code == 200

    units_r = await client.get(
        "/api/v1/translations/", params={"target_language": "es-ES", "limit": 50},
    )
    fixture_units = [
        u for u in units_r.json()
        if u["source_text"] in ("Pending Fixture Heading", "Pending fixture paragraph.")
    ]
    assert len(fixture_units) == 2

    # No pending changes yet.
    pending_r = await client.get(
        "/api/v1/pages/pending", params={"url": pending_fixture_server, "target_language": "es-ES"},
    )
    assert pending_r.status_code == 200
    assert pending_r.json()["pending"] == []

    # has_pending_proposal is false before any proposal exists.
    batch_r = await client.get(
        "/api/v1/translations/batch", params={"ids": ",".join(u["id"] for u in fixture_units)},
    )
    assert all(u["has_pending_proposal"] is False for u in batch_r.json())

    # Propose a translation for both units.
    items = []
    for unit in fixture_units:
        r = await client.post(
            "/api/v1/redrive/propose",
            json={"unit_id": unit["id"], "proposed_text": f"Propuesta: {unit['source_text']}", "proposed_by": "editor@example.com"},
        )
        assert r.status_code == 201
        items.append(r.json())

    # Now both show up as pending on the page, and the batch flag flips.
    pending_r2 = await client.get(
        "/api/v1/pages/pending", params={"url": pending_fixture_server, "target_language": "es-ES"},
    )
    pending = pending_r2.json()["pending"]
    assert len(pending) == 2
    assert {p["unit_id"] for p in pending} == {u["id"] for u in fixture_units}
    assert all(p["proposed_text"].startswith("Propuesta:") for p in pending)

    batch_r2 = await client.get(
        "/api/v1/translations/batch", params={"ids": ",".join(u["id"] for u in fixture_units)},
    )
    assert all(u["has_pending_proposal"] is True for u in batch_r2.json())

    # Bulk-approve both in one call.
    bulk_r = await client.post(
        "/api/v1/redrive/items/bulk-approve",
        json={"item_ids": [i["id"] for i in items], "actor": "editor@example.com"},
    )
    assert bulk_r.status_code == 200
    results = bulk_r.json()["results"]
    assert len(results) == 2
    assert all(r["ok"] for r in results)
    assert all(r["item"]["outcome"] == "redriven" for r in results)

    # Applied for real, and no longer pending.
    for unit in fixture_units:
        u = (await client.get(f"/api/v1/translations/{unit['id']}")).json()
        assert u["target_text"] == f"Propuesta: {unit['source_text']}"

    pending_r3 = await client.get(
        "/api/v1/pages/pending", params={"url": pending_fixture_server, "target_language": "es-ES"},
    )
    assert pending_r3.json()["pending"] == []


@pytest.mark.asyncio
async def test_bulk_approve_reports_failure_for_unknown_item(client):
    r = await client.post(
        "/api/v1/redrive/items/bulk-approve",
        json={"item_ids": ["does-not-exist"], "actor": "editor@example.com"},
    )
    assert r.status_code == 200
    results = r.json()["results"]
    assert len(results) == 1
    assert results[0]["ok"] is False


@pytest.mark.asyncio
async def test_pending_404s_for_unknown_page(client):
    r = await client.get(
        "/api/v1/pages/pending", params={"url": "http://example.invalid/never-fetched", "target_language": "fr-FR"},
    )
    assert r.status_code == 404
