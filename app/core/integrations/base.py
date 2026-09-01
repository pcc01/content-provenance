"""CMSIntegration — the provider contract every CMS connector implements.

Same "one small ABC + a factory picking a concrete implementation" shape
already used for translation providers (app/core/translation_backends.py's
TranslationBackend). A CMS entry is addressed by (content_type, entry_id,
field); `locale` is optional on both operations because how — or whether —
a provider even needs it varies:

  Strapi  — a query-string `?locale=xx` selects the locale-variant of the
            entry to read/write (i18n plugin, on by default in modern
            Strapi).
  Payload — same shape as Strapi: `?locale=xx` on both GET and PATCH.
  Directus — no universal `locale` param at all; localization is schema-
            dependent (typically a `{collection}_translations` junction
            table), so a real Directus integration needs its own mapping
            config, not just a query param. See factory.py's docstring on
            get_cms_integration for the full note — not implemented yet.

Every method should raise ValueError (not a provider-specific exception)
on any failure — config problems, network errors, non-2xx responses —
matching this codebase's existing service-layer convention of the API
layer catching plain ValueError and mapping it to an HTTPException (see
app/api/redrive.py).
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Mapping, Optional

from pydantic import BaseModel


class CMSIntegration(ABC):
    provider: str

    @abstractmethod
    async def push_field(
        self,
        content_type: str,
        entry_id: str,
        field: str,
        value: str,
        locale: Optional[str] = None,
        extra_fields: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Write `field` (and any `extra_fields` — e.g. the provenance
        field) into one entry in a single request. Returns the CMS's raw
        response body (used for confirmation/debugging, not parsed further
        by callers)."""
        raise NotImplementedError

    @abstractmethod
    async def pull_field(
        self,
        content_type: str,
        entry_id: str,
        field: str,
        locale: Optional[str] = None,
    ) -> Optional[str]:
        """Read `field`'s current value from one entry. None if the entry
        or field doesn't exist / is empty."""
        raise NotImplementedError


# ── TMS integration ────────────────────────────────────────────────────────
#
# A TMS (Crowdin, Phrase, Lokalise, ...) manages the translation/review
# WORKFLOW around content — distinct from a CMS, which publishes it. The
# contract is one level up from CMSIntegration's single-field push/pull:
# source strings, translation suggestions, review comments, approved-
# translation retrieval, and a webhook for approval events. Same failure
# convention — every method raises plain ValueError (the API layer maps it
# to an HTTPException), see app/api/tms.py.


class TMSApprovalEvent(BaseModel):
    """Normalized "a translation was approved" signal, parsed out of a
    provider's webhook payload (or a polling result). `key` is the stable
    string identifier we set on push — the TranslationUnit id."""
    key: str
    language: str            # the provider's own language/locale code
    approved_text: str
    translator: Optional[str] = None


class TMSIntegration(ABC):
    provider: str

    @abstractmethod
    async def upsert_source_string(
        self, *, key: str, text: str,
        context: Optional[str] = None, max_length: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Create the source string, or update it if one with this `key`
        (stable identifier) already exists. Returns {"string_id": ..., ...}."""
        raise NotImplementedError

    @abstractmethod
    async def add_suggestion(self, *, string_id: str, language: str, text: str) -> Dict[str, Any]:
        """Add a machine-translation draft as a translation suggestion for
        a reviewer to accept or edit."""
        raise NotImplementedError

    @abstractmethod
    async def add_comment(self, *, string_id: str, text: str) -> Dict[str, Any]:
        """Attach a note (quality score / model / flags) visible in the TMS
        editor next to the string."""
        raise NotImplementedError

    @abstractmethod
    async def fetch_approved_translation(self, *, key: str, language: str) -> Optional[str]:
        """The current approved translation for the string with this stable
        `key` (identifier) + language, or None. The polling fallback for
        deployments without a public webhook."""
        raise NotImplementedError

    @abstractmethod
    async def ensure_webhook(self, *, callback_url: str, events: List[str]) -> Dict[str, Any]:
        """Register a project webhook at `callback_url` for `events`,
        idempotently (a no-op if one with the same URL already exists)."""
        raise NotImplementedError

    @abstractmethod
    def parse_webhook_event(
        self, headers: Mapping[str, str], body: bytes, secret: str,
    ) -> Optional[TMSApprovalEvent]:
        """Verify an inbound webhook (raise ValueError on a bad signature)
        and parse it. Returns a TMSApprovalEvent for an approval event, or
        None for events we don't act on."""
        raise NotImplementedError
