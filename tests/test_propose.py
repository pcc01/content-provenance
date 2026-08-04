"""
Tests for Phase 10's live-drafting endpoint: a human proposes their own
translation for a segment, which goes through the same human-in-the-loop
approval mechanism as a scorer-triggered redrive.
Run with: PYTHONPATH=. pytest tests/test_propose.py -v
"""

import pytest


@pytest.mark.asyncio
async def test_propose_creates_pending_approval_item(client):
    payload = {
        "source_text": "Propose test source.",
        "source_language": "en-US",
        "target_language": "fr-FR",
        "method": "ai",
        "context": "website",
    }
    unit_id = (await client.post("/api/v1/translations/", json=payload)).json()["translation_unit_id"]
    original_target = (await client.get(f"/api/v1/translations/{unit_id}")).json()["target_text"]

    r = await client.post(
        "/api/v1/redrive/propose",
        json={"unit_id": unit_id, "proposed_text": "Ma propre traduction.", "proposed_by": "reviewer@example.com"},
    )
    assert r.status_code == 201
    item = r.json()
    assert item["outcome"] == "pending_approval"
    assert item["proposed_text"] == "Ma propre traduction."

    # The unit itself is untouched until someone approves.
    unit_r = await client.get(f"/api/v1/translations/{unit_id}")
    assert unit_r.json()["target_text"] == original_target

    run_r = await client.get(f"/api/v1/redrive/runs/{item['run_id']}")
    run = run_r.json()
    assert run["scoring_provider"] == "human"
    assert run["redrive_provider"] == "human"
    assert run["require_human_approval"] is True


@pytest.mark.asyncio
async def test_propose_then_approve_applies_text_and_labels_it_human(client):
    payload = {
        "source_text": "Approve human draft test.",
        "source_language": "en-US",
        "target_language": "de-DE",
        "method": "ai",
        "context": "website",
    }
    unit_id = (await client.post("/api/v1/translations/", json=payload)).json()["translation_unit_id"]

    propose_r = await client.post(
        "/api/v1/redrive/propose",
        json={"unit_id": unit_id, "proposed_text": "Mein eigener Entwurf.", "proposed_by": "reviewer@example.com"},
    )
    item = propose_r.json()

    approve_r = await client.post(
        f"/api/v1/redrive/runs/{item['run_id']}/items/{item['id']}/approve",
        json={"actor": "reviewer@example.com"},
    )
    assert approve_r.status_code == 200
    approved = approve_r.json()
    assert approved["outcome"] == "redriven"

    unit_r = await client.get(f"/api/v1/translations/{unit_id}")
    assert unit_r.json()["target_text"] == "Mein eigener Entwurf."

    versions_r = await client.get(f"/api/v1/translations/{unit_id}/versions")
    versions = versions_r.json()
    latest_note = versions[-1]["note"] or ""
    # The whole point of the redrive_label fix: this must say "human", not
    # whatever TranslationBackend happens to be globally configured (mock).
    assert "Redriven via human" in latest_note
    assert "approved by reviewer@example.com" in latest_note


@pytest.mark.asyncio
async def test_propose_reject_leaves_unit_untouched(client):
    payload = {
        "source_text": "Reject human draft test.",
        "source_language": "en-US",
        "target_language": "ja-JP",
        "method": "ai",
        "context": "website",
    }
    unit_id = (await client.post("/api/v1/translations/", json=payload)).json()["translation_unit_id"]
    original_target = (await client.get(f"/api/v1/translations/{unit_id}")).json()["target_text"]

    item = (
        await client.post(
            "/api/v1/redrive/propose",
            json={"unit_id": unit_id, "proposed_text": "却下されるべき提案。", "proposed_by": "reviewer@example.com"},
        )
    ).json()

    reject_r = await client.post(
        f"/api/v1/redrive/runs/{item['run_id']}/items/{item['id']}/reject",
        json={"actor": "senior@example.com", "reason": "not accurate"},
    )
    assert reject_r.status_code == 200
    assert reject_r.json()["outcome"] == "rejected"

    unit_r = await client.get(f"/api/v1/translations/{unit_id}")
    assert unit_r.json()["target_text"] == original_target


@pytest.mark.asyncio
async def test_propose_rejects_unknown_unit(client):
    r = await client.post(
        "/api/v1/redrive/propose",
        json={"unit_id": "does-not-exist", "proposed_text": "x", "proposed_by": "reviewer@example.com"},
    )
    assert r.status_code == 404
