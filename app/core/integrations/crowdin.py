"""CrowdinIntegration — the first working TMSIntegration provider.

Raw httpx against Crowdin REST API v2, no SDK (same bare-REST choice as
StrapiIntegration / app/core/llm_clients.py). A source string is addressed
by `identifier`, which we set to the TranslationUnit id — so a round-trip
(push string -> reviewer approves -> webhook) can find its way home.

Endpoints used (base `https://api.crowdin.com/api/v2`, Bearer token):
  GET/POST   /projects/{pid}/strings              find-by-identifier / create
  PATCH      /projects/{pid}/strings/{id}         update text/context (JSON Patch)
  POST       /projects/{pid}/translations         add a suggestion for a language
  POST       /projects/{pid}/comments             attach a note to a string
  GET        /projects/{pid}/approvals            approved translation id for a string+lang
  GET        /projects/{pid}/translations/{id}    -> the approved text
  GET/POST   /projects/{pid}/webhooks             register the approval webhook

Webhook auth is a shared `?secret=` on the callback URL, checked by the API
layer (app/api/tms.py). parse_webhook_event here only parses; it additionally
honours an `X-Crowdin-Signature` HMAC header if a Crowdin Enterprise project
sends one.

The exact language-id rule and a couple of payload keys are confirmed
against the live project during verification (see the plan's Verification
section); anything uncertain is flagged inline.
"""

import hashlib
import hmac
import json
from typing import Any, Dict, List, Mapping, Optional

import httpx

from app.core.integrations.base import TMSApprovalEvent, TMSIntegration

# Crowdin language IDs are mostly the ISO-639-1 subtag ("fr", "de"), but
# regional for languages Crowdin splits by locale. Kept as data so a
# project that uses different ids is a one-line change here.
_CROWDIN_REGIONAL = {
    "pt-BR", "pt-PT", "zh-CN", "zh-TW", "es-ES", "es-MX",
    "en-US", "en-GB", "fr-CA", "fr-QC", "nb-NO", "sr-CS",
}


def crowdin_lang(locale: str) -> str:
    """Map an app locale ("fr-FR", "pt-BR") to a Crowdin language id."""
    locale = (locale or "").strip()
    if locale in _CROWDIN_REGIONAL:
        return locale
    return locale.split("-")[0].lower()


class CrowdinIntegration(TMSIntegration):
    provider = "crowdin"

    def __init__(
        self, base_url: str, project_id: str, api_token: str,
        branch: str = "", timeout: float = 20.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.project_id = str(project_id)
        self.api_token = api_token
        self.branch_name = branch or ""
        self._branch_id: Optional[int] = None
        self.timeout = timeout

    # ── source strings ───────────────────────────────────────────────────

    async def _resolve_branch_id(self) -> int:
        """String-based projects attach strings to a branch. Resolve (and
        cache) the configured branch by name, or the project's first branch,
        creating a 'content-provenance' branch only if the project has none."""
        if self._branch_id is not None:
            return self._branch_id
        raw = await self._request(
            "GET", f"/projects/{self.project_id}/branches", params={"limit": 100},
        )
        branches = [row.get("data", row) for row in raw.get("data", [])]
        if self.branch_name:
            for b in branches:
                if b.get("name") == self.branch_name:
                    self._branch_id = int(b["id"])
                    return self._branch_id
            created = await self._request(
                "POST", f"/projects/{self.project_id}/branches",
                json={"name": self.branch_name},
            )
            self._branch_id = int(_data(created)["id"])
            return self._branch_id
        if branches:
            self._branch_id = int(branches[0]["id"])
            return self._branch_id
        created = await self._request(
            "POST", f"/projects/{self.project_id}/branches",
            json={"name": "content-provenance"},
        )
        self._branch_id = int(_data(created)["id"])
        return self._branch_id

    async def upsert_source_string(
        self, *, key: str, text: str,
        context: Optional[str] = None, max_length: Optional[int] = None,
    ) -> Dict[str, Any]:
        existing = await self._find_string(key)
        if existing:
            sid = existing["id"]
            patch: List[Dict[str, Any]] = [{"op": "replace", "path": "/text", "value": text}]
            if context is not None:
                patch.append({"op": "replace", "path": "/context", "value": context})
            raw = await self._request("PATCH", f"/projects/{self.project_id}/strings/{sid}", json=patch)
            return {"string_id": str(sid), "created": False, "raw": raw}

        body: Dict[str, Any] = {"text": text, "identifier": key, "branchId": await self._resolve_branch_id()}
        if context is not None:
            body["context"] = context
        if max_length is not None:
            body["maxLength"] = max_length
        raw = await self._request("POST", f"/projects/{self.project_id}/strings", json=body)
        return {"string_id": str(_data(raw).get("id")), "created": True, "raw": raw}

    async def _find_string(self, identifier: str) -> Optional[Dict[str, Any]]:
        raw = await self._request(
            "GET", f"/projects/{self.project_id}/strings",
            params={
                "filter": identifier, "scope": "identifier", "limit": 50,
                "branchId": await self._resolve_branch_id(),
            },
        )
        for row in raw.get("data", []):
            d = row.get("data", row)
            if d.get("identifier") == identifier:
                return d
        return None

    # ── suggestions + comments ───────────────────────────────────────────

    async def add_suggestion(self, *, string_id: str, language: str, text: str) -> Dict[str, Any]:
        try:
            return await self._request(
                "POST", f"/projects/{self.project_id}/translations",
                json={"stringId": int(string_id), "languageId": crowdin_lang(language), "text": text},
            )
        except ValueError as exc:
            # An identical suggestion already exists — not an error for our
            # purposes, the string is in Crowdin and reviewable.
            if "Duplicate translation" in str(exc):
                return {"duplicate": True}
            raise

    async def add_comment(self, *, string_id: str, text: str) -> Dict[str, Any]:
        return await self._request(
            "POST", f"/projects/{self.project_id}/comments",
            json={"stringId": int(string_id), "text": text, "type": "comment"},
        )

    # ── approved-translation retrieval (polling fallback) ─────────────────

    async def fetch_approved_translation(self, *, key: str, language: str) -> Optional[str]:
        found = await self._find_string(key)
        if not found:
            return None
        string_id = found["id"]
        raw = await self._request(
            "GET", f"/projects/{self.project_id}/approvals",
            params={"stringId": int(string_id), "languageId": crowdin_lang(language), "limit": 1},
        )
        rows = raw.get("data", [])
        if not rows:
            return None
        translation_id = (rows[0].get("data", rows[0]) or {}).get("translationId")
        if not translation_id:
            return None
        tdata = await self._request("GET", f"/projects/{self.project_id}/translations/{translation_id}")
        return _data(tdata).get("text")

    # ── webhooks ─────────────────────────────────────────────────────────

    async def ensure_webhook(self, *, callback_url: str, events: List[str]) -> Dict[str, Any]:
        existing = await self._request(
            "GET", f"/projects/{self.project_id}/webhooks", params={"limit": 100},
        )
        for row in existing.get("data", []):
            d = row.get("data", row)
            if d.get("url") == callback_url:
                return {"webhook_id": str(d.get("id")), "created": False}
        raw = await self._request(
            "POST", f"/projects/{self.project_id}/webhooks",
            json={
                "name": "Content Provenance",
                "url": callback_url,
                "events": events,
                "requestType": "POST",
                "contentType": "application/json",
                "isActive": True,
                "batchingEnabled": False,
            },
        )
        return {"webhook_id": str(_data(raw).get("id")), "created": True}

    def parse_webhook_event(
        self, headers: Mapping[str, str], body: bytes, secret: str,
    ) -> Optional[TMSApprovalEvent]:
        # Enterprise projects can HMAC-sign the body; verify it if present.
        sig = headers.get("x-crowdin-signature") or headers.get("X-Crowdin-Signature")
        if sig and secret:
            expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(sig, expected):
                raise ValueError("Crowdin webhook signature mismatch")

        try:
            payload = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValueError(f"Crowdin webhook body is not JSON: {exc}") from exc

        if isinstance(payload, list):
            events = payload
        elif isinstance(payload, dict) and isinstance(payload.get("events"), list):
            events = payload["events"]
        else:
            events = [payload]

        for ev in events:
            if not isinstance(ev, dict):
                continue
            if ev.get("event") != "suggestion.approved":
                continue
            entity = ev.get("suggestion") or ev.get("translation") or {}
            string = entity.get("string") or {}
            identifier = string.get("identifier")
            text = entity.get("text")
            lang = (entity.get("targetLanguage") or entity.get("language") or {}).get("id")
            translator = (entity.get("user") or {}).get("username")
            if identifier and text and lang:
                return TMSApprovalEvent(
                    key=identifier, language=str(lang), approved_text=text, translator=translator,
                )
        return None

    # ── private ──────────────────────────────────────────────────────────

    async def _request(
        self, method: str, path: str, *,
        params: Optional[Dict[str, Any]] = None, json: Any = None,
    ) -> Dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.api_token}"}
        if json is not None:
            headers["Content-Type"] = "application/json"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.request(
                    method, f"{self.base_url}{path}", headers=headers, params=params, json=json,
                )
                if resp.status_code == 404 and method == "GET":
                    return {"data": []}
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise ValueError(
                    f"Crowdin rejected {method} {path}: "
                    f"{exc.response.status_code} {exc.response.text[:300]}"
                ) from exc
            except httpx.RequestError as exc:
                raise ValueError(f"Could not reach Crowdin at {self.base_url}: {exc}") from exc
        if resp.status_code == 204 or not resp.content:
            return {}
        return resp.json()


def _data(body: Dict[str, Any]) -> Dict[str, Any]:
    """Crowdin wraps single objects as {"data": {...}}."""
    d = body.get("data") if isinstance(body, dict) else None
    return d if isinstance(d, dict) else {}
