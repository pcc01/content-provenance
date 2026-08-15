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
from typing import Any, Dict, Optional


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
