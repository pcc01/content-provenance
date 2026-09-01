"""get_cms_integration(provider) / get_tms_integration(provider) — pick the
active CMS / TMS connector, same "one active provider, selectable, more can
be added later" shape as app/core/translation_backends.py's
get_translation_backend.

CMS: only Strapi works today; Directus/Payload fail loudly with what's
missing rather than silently falling through.

TMS: only Crowdin works today; Phrase/Lokalise/Transifex are shaped for by
the TMSIntegration contract but not built.
"""

from typing import Optional

from app.core.config import settings
from app.core.integrations.base import CMSIntegration, TMSIntegration
from app.core.integrations.crowdin import CrowdinIntegration
from app.core.integrations.strapi import StrapiIntegration


def get_cms_integration(provider: Optional[str] = None) -> CMSIntegration:
    provider = (provider or settings.cms_provider or "strapi").lower()

    if provider == "strapi":
        if not settings.strapi_base_url or not settings.strapi_api_token:
            raise ValueError(
                "Strapi integration is not configured — set STRAPI_BASE_URL and "
                "STRAPI_API_TOKEN (see .env.example)."
            )
        return StrapiIntegration(
            base_url=settings.strapi_base_url,
            api_token=settings.strapi_api_token,
            timeout=settings.strapi_timeout_seconds,
        )

    if provider == "directus":
        # Directus uses the same {"data": {...}} wrapper Strapi does on
        # read/write, but has no universal `locale` query param — most
        # Directus schemas model localization as a separate
        # `{collection}_translations` junction collection
        # ({collection}_id, languages_code, the localized fields
        # themselves). A real integration needs a small mapping config
        # (translation_collection / parent_field / locale_field), not just
        # a URL param swap — that's the next real build here, not a stub
        # worth half-implementing.
        raise ValueError("directus CMS integration is not implemented yet")

    if provider == "payload":
        # Closest to Strapi of the two: flat body (no "data" wrapper) on
        # GET/PATCH /api/{collection}/{id}, ?locale=xx on both, same
        # Bearer-token auth shape — a PayloadIntegration should be a small,
        # mechanical port of StrapiIntegration once there's a live
        # instance to build/test against.
        raise ValueError("payload CMS integration is not implemented yet")

    raise ValueError(f"Unknown CMS provider: {provider!r} (known: strapi, directus, payload)")


def get_tms_integration(provider: Optional[str] = None) -> TMSIntegration:
    provider = (provider or settings.tms_provider or "crowdin").lower()

    if provider == "crowdin":
        if not settings.crowdin_project_id or not settings.crowdin_api_token:
            raise ValueError(
                "Crowdin integration is not configured — set CROWDIN_PROJECT_ID and "
                "CROWDIN_API_TOKEN (see .env.example)."
            )
        return CrowdinIntegration(
            base_url=settings.crowdin_base_url,
            project_id=settings.crowdin_project_id,
            api_token=settings.crowdin_api_token,
            timeout=settings.crowdin_timeout_seconds,
        )

    if provider in ("phrase", "lokalise", "transifex"):
        raise ValueError(f"{provider} TMS integration is not implemented yet")

    raise ValueError(f"Unknown TMS provider: {provider!r} (known: crowdin)")
