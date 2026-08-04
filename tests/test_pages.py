"""
Tests for the pages API (Phase 8): fetch + rewrite review for arbitrary
URLs — a real headless-browser render against a local static fixture
server, so these are slower than the rest of the suite by nature.
Run with: PYTHONPATH=. pytest tests/test_pages.py -v
"""

import functools
import http.server
import tempfile
import threading
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
