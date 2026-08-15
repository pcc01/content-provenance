#!/usr/bin/env python
"""
Bootstrap a local Strapi instance (docker-compose --profile cms up -d
strapi) into a working example for testing this app's CMS integration
(app/core/integrations/strapi.py) end-to-end, with no manual clicking
through Strapi's admin UI required:

  1. Wait for Strapi to finish booting (first boot scaffolds its own
     project on disk — can take a minute or two).
  2. Register the first admin account (or log in, if one already exists).
  3. Create a demo "translation-example" content type via Strapi's
     Content-Type Builder API (title, body, content_provenance fields).
  4. Create a full-access API token.
  5. Create one demo entry in Strapi.
  6. Print the exact .env lines to set (STRAPI_BASE_URL/STRAPI_API_TOKEN)
     and the content_type/entry_id/field_name to use with
     POST /api/v1/integrations/cms/push.

Optionally (--verify), also drives THIS app's own API: creates a
TranslationUnit, pushes it into the demo Strapi entry via
POST /api/v1/integrations/cms/push, then reads the entry back from Strapi
to confirm both the translated field and the provenance field actually
landed there — a genuine end-to-end smoke test, not just "the script ran."

Usage:
    python scripts/bootstrap_strapi.py
    python scripts/bootstrap_strapi.py --verify
    python scripts/bootstrap_strapi.py --strapi-url http://localhost:1337 \\
        --admin-email admin@example.com --admin-password "ChangeMe123!"

Requires: httpx (already a project dependency — see requirements.txt).
"""

import argparse
import sys
import time

import httpx

# Windows' default console codepage (cp1252) can't encode the checkmark
# below — same fix app/main.py already applies to its own startup logs.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

CONTENT_TYPE_SINGULAR = "translation-example"
CONTENT_TYPE_PLURAL = "translation-examples"
DEMO_FIELD = "body"


def log(msg: str) -> None:
    print(f"[bootstrap-strapi] {msg}", flush=True)


def wait_for_strapi(base_url: str, timeout: float) -> dict:
    """Polls /admin/init until Strapi responds — first boot scaffolds the
    whole project on disk, which can take a while. Returns the parsed
    {"data": {"hasAdmin": bool, ...}} body once ready."""
    log(f"Waiting for Strapi at {base_url} (up to {int(timeout)}s — first boot is slow)...")
    deadline = time.monotonic() + timeout
    last_error = None
    with httpx.Client(timeout=5.0) as client:
        while time.monotonic() < deadline:
            try:
                resp = client.get(f"{base_url}/admin/init")
                if resp.status_code == 200:
                    log("Strapi is up.")
                    return resp.json()
                last_error = f"HTTP {resp.status_code}"
            except httpx.RequestError as exc:
                last_error = str(exc)
            time.sleep(3)
    raise SystemExit(f"Strapi never became ready at {base_url}: {last_error}")


def get_admin_token(client: httpx.Client, base_url: str, init_data: dict, email: str, password: str) -> str:
    has_admin = init_data.get("data", {}).get("hasAdmin", False)
    if not has_admin:
        log(f"No admin account yet — registering {email} ...")
        resp = client.post(f"{base_url}/admin/register-admin", json={
            "firstname": "Content", "lastname": "Provenance",
            "email": email, "password": password,
        })
        if resp.status_code >= 400:
            raise SystemExit(f"Admin registration failed: {resp.status_code} {resp.text[:400]}")
        return resp.json()["data"]["token"]

    log(f"Admin account already exists — logging in as {email} ...")
    resp = client.post(f"{base_url}/admin/login", json={"email": email, "password": password})
    if resp.status_code >= 400:
        raise SystemExit(
            "Login failed — an admin account already exists but doesn't match "
            f"--admin-email/--admin-password. ({resp.status_code} {resp.text[:400]})"
        )
    return resp.json()["data"]["token"]


def ensure_content_type(client: httpx.Client, base_url: str, admin_token: str) -> None:
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Already there from a previous run of this script? Skip creating it —
    # the Content-Type Builder API doesn't offer a clean idempotent create.
    existing = client.get(f"{base_url}/content-type-builder/content-types", headers=headers)
    if existing.status_code == 200:
        uids = {ct.get("uid", "") for ct in existing.json().get("data", [])}
        if f"api::{CONTENT_TYPE_SINGULAR}.{CONTENT_TYPE_SINGULAR}" in uids:
            log(f"Content type '{CONTENT_TYPE_SINGULAR}' already exists — skipping creation.")
            return

    log(f"Creating content type '{CONTENT_TYPE_SINGULAR}' (title, body, content_provenance)...")
    # singularName/pluralName/displayName go directly on contentType, NOT
    # nested under an "info" object — verified against a real 5.52.0
    # instance; the nested-under-info shape (the v4 convention this
    # started from) 400s with "singularName is a required field".
    payload = {
        "contentType": {
            "kind": "collectionType",
            "collectionName": "translation_examples",
            "singularName": CONTENT_TYPE_SINGULAR,
            "pluralName": CONTENT_TYPE_PLURAL,
            "displayName": "Translation Example",
            "description": "Demo content type for content-provenance's Strapi integration testing.",
            "options": {"draftAndPublish": False},
            "attributes": {
                "title": {"type": "string"},
                "body": {"type": "text"},
                "content_provenance": {"type": "json"},
            },
        }
    }
    resp = client.post(f"{base_url}/content-type-builder/content-types", headers=headers, json=payload)
    if resp.status_code >= 400:
        raise SystemExit(f"Content type creation failed: {resp.status_code} {resp.text[:400]}")

    # Creating a content type restarts Strapi's server process internally.
    log("Content type created — waiting for Strapi to restart...")
    time.sleep(5)
    wait_for_strapi(base_url, timeout=90)


def create_api_token(client: httpx.Client, base_url: str, admin_token: str) -> str:
    log("Creating a full-access API token...")
    resp = client.post(
        f"{base_url}/admin/api-tokens",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "name": f"content-provenance-bootstrap-{int(time.time())}",
            "description": "Created by scripts/bootstrap_strapi.py",
            "type": "full-access",
            "lifespan": None,
        },
    )
    if resp.status_code >= 400:
        raise SystemExit(f"API token creation failed: {resp.status_code} {resp.text[:400]}")
    # The token value comes back as "accessKey" on this endpoint — NOT
    # "accessToken" (that field name belongs to /admin/login's response,
    # a different token entirely) — verified against a real 5.52.0 instance.
    return resp.json()["data"]["accessKey"]


def create_demo_entry(client: httpx.Client, base_url: str, api_token: str) -> str:
    log("Creating one demo entry...")
    resp = client.post(
        f"{base_url}/api/{CONTENT_TYPE_PLURAL}",
        headers={"Authorization": f"Bearer {api_token}"},
        json={"data": {"title": "content-provenance demo entry", DEMO_FIELD: "(untranslated placeholder)"}},
    )
    if resp.status_code >= 400:
        raise SystemExit(f"Demo entry creation failed: {resp.status_code} {resp.text[:400]}")
    data = resp.json()["data"]
    # v5 identifies entries by documentId; v4 by a numeric id. Either works
    # as {entry_id} in this app's push/pull calls — Strapi accepts both on
    # GET/PUT for a v5 instance, and v4 only ever has the numeric id.
    entry_id = data.get("documentId") or data.get("id")
    return str(entry_id)


def verify_via_content_provenance(app_url: str, strapi_url: str, strapi_token: str, entry_id: str) -> None:
    """Drives THIS app's own API to prove the full pipeline: create a
    translation, push it into the demo Strapi entry, then read the entry
    back from Strapi directly to confirm both fields actually landed."""
    log(f"Verifying end-to-end against content-provenance at {app_url} ...")
    with httpx.Client(timeout=30.0) as client:
        create_resp = client.post(f"{app_url}/api/v1/translations/", json={
            "source_text": "Bootstrap verification content.",
            "source_language": "en-US", "target_language": "fr-FR",
            "method": "ai", "context": "website",
        })
        if create_resp.status_code >= 400:
            raise SystemExit(
                f"Could not create a translation on {app_url} — is the app running? "
                f"({create_resp.status_code} {create_resp.text[:300]})"
            )
        unit_id = create_resp.json()["translation_unit_id"]
        # Whatever the configured TRANSLATION_PROVIDER actually produced —
        # the mock backend prefixes "[FR] " etc., a real provider wouldn't —
        # so compare against this rather than the literal source text.
        translated_text = create_resp.json()["translated_text"]
        log(f"Created translation unit {unit_id} (translated: {translated_text!r}).")

        push_resp = client.post(f"{app_url}/api/v1/integrations/cms/push", json={
            "unit_id": unit_id, "provider": "strapi", "content_type": CONTENT_TYPE_PLURAL,
            "entry_id": entry_id, "field_name": DEMO_FIELD,
        })
        if push_resp.status_code >= 400:
            raise SystemExit(f"Push failed: {push_resp.status_code} {push_resp.text[:400]}")
        log(f"Pushed to Strapi — deployment_id={push_resp.json()['deployment_id']}")

    with httpx.Client(timeout=15.0) as client:
        entry_resp = client.get(
            f"{strapi_url}/api/{CONTENT_TYPE_PLURAL}/{entry_id}",
            headers={"Authorization": f"Bearer {strapi_token}"},
        )
        entry_resp.raise_for_status()
        body = entry_resp.json()["data"]
        attrs = body.get("attributes", body)
        assert attrs.get(DEMO_FIELD) == translated_text, (
            f"Strapi entry's '{DEMO_FIELD}' field doesn't match what was pushed: "
            f"{attrs.get(DEMO_FIELD)!r} != {translated_text!r}"
        )
        assert attrs.get("content_provenance", {}).get("bundle_id"), "content_provenance field is missing/empty"
    log("Verified: the translated text AND the provenance record both landed in the Strapi entry. ✓")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--strapi-url", default="http://localhost:1337")
    parser.add_argument("--app-url", default="http://localhost:8001", help="This app's own base URL (for --verify).")
    parser.add_argument("--admin-email", default="admin@content-provenance.local")
    parser.add_argument("--admin-password", default="Bootstrap123!Strapi")
    parser.add_argument("--timeout", type=float, default=120.0, help="Seconds to wait for Strapi to boot.")
    parser.add_argument("--verify", action="store_true", help="Also push a real translation through the app end-to-end.")
    args = parser.parse_args()

    init_data = wait_for_strapi(args.strapi_url, args.timeout)
    with httpx.Client(timeout=30.0) as client:
        admin_token = get_admin_token(client, args.strapi_url, init_data, args.admin_email, args.admin_password)
        ensure_content_type(client, args.strapi_url, admin_token)
        api_token = create_api_token(client, args.strapi_url, admin_token)
        entry_id = create_demo_entry(client, args.strapi_url, api_token)

    print()
    log("Done. Add these to your .env:")
    print(f"\n    STRAPI_BASE_URL={args.strapi_url}")
    print(f"    STRAPI_API_TOKEN={api_token}\n")
    log(
        f"Demo entry ready to push into: content_type={CONTENT_TYPE_PLURAL} "
        f"entry_id={entry_id} field_name={DEMO_FIELD}"
    )
    log(
        "Try it: POST /api/v1/integrations/cms/push "
        f'{{"unit_id": "...", "content_type": "{CONTENT_TYPE_PLURAL}", '
        f'"entry_id": "{entry_id}", "field_name": "{DEMO_FIELD}"}}'
    )

    if args.verify:
        print()
        verify_via_content_provenance(args.app_url, args.strapi_url, api_token, entry_id)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
