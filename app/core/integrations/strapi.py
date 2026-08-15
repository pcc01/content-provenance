"""StrapiIntegration — the first working CMSIntegration provider.

Raw httpx calls, no SDK dependency (same bare-REST-client choice already
made in app/core/llm_clients.py for the translation/scoring providers).

REST shape (works for both Strapi v4 and v5):
  PUT  {base_url}/api/{content_type}/{entry_id}[?locale=xx]
       body: {"data": {field: value, ...extra_fields}}
  GET  {base_url}/api/{content_type}/{entry_id}[?locale=xx]
       response: v4 nests fields under data.attributes; v5 flattened that
       away. _unwrap_entry() below handles either shape so this doesn't
       silently break across a Strapi version upgrade.
Auth: Authorization: Bearer {api_token} (Settings -> API Tokens in Strapi's
admin panel; needs read+write permission on the target content type).
"""

from typing import Any, Dict, Optional

import httpx

from app.core.integrations.base import CMSIntegration


class StrapiIntegration(CMSIntegration):
    provider = "strapi"

    def __init__(self, base_url: str, api_token: str, timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self.timeout = timeout

    async def push_field(
        self,
        content_type: str,
        entry_id: str,
        field: str,
        value: str,
        locale: Optional[str] = None,
        extra_fields: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        body = {field: value, **(extra_fields or {})}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.put(
                    self._url(content_type, entry_id),
                    headers=self._headers(),
                    params=self._params(locale),
                    json={"data": body},
                )
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise ValueError(self._status_error("write to", content_type, entry_id, exc)) from exc
            except httpx.RequestError as exc:
                raise ValueError(self._connection_error(exc)) from exc
        return resp.json()

    async def pull_field(
        self,
        content_type: str,
        entry_id: str,
        field: str,
        locale: Optional[str] = None,
    ) -> Optional[str]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.get(
                    self._url(content_type, entry_id),
                    headers=self._headers(),
                    params=self._params(locale),
                )
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise ValueError(self._status_error("read of", content_type, entry_id, exc)) from exc
            except httpx.RequestError as exc:
                raise ValueError(self._connection_error(exc)) from exc

        entry = _unwrap_entry(resp.json())
        if entry is None:
            return None
        value = entry.get(field)
        return value if isinstance(value, str) and value else None

    # ── Private helpers ───────────────────────────────────────────────────

    def _url(self, content_type: str, entry_id: str) -> str:
        return f"{self.base_url}/api/{content_type}/{entry_id}"

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_token}"}

    @staticmethod
    def _params(locale: Optional[str]) -> Optional[Dict[str, str]]:
        return {"locale": locale} if locale else None

    @staticmethod
    def _status_error(action: str, content_type: str, entry_id: str, exc: httpx.HTTPStatusError) -> str:
        return (
            f"Strapi rejected the {action} {content_type}/{entry_id}: "
            f"{exc.response.status_code} {exc.response.text[:300]}"
        )

    def _connection_error(self, exc: httpx.RequestError) -> str:
        return f"Could not reach Strapi at {self.base_url}: {exc}"


def _unwrap_entry(body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    data = body.get("data")
    if not isinstance(data, dict):
        return None
    return data.get("attributes", data)
