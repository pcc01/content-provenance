"""
Phase 12 — region -> applicable privacy regulation mapping, backed by real
jurisdiction reference data (app/core/audit/data/jurisdictions/*.json) —
ported from the user's own privacy-compliance engine built for
peripateticware (backend/services/privacy_jurisdiction_resolver.py +
backend/config/jurisdictions/). That system is a full live service tied to
peripateticware's own domain (schools/orgs, a Postgres catalog, an
AI-discovery pipeline for unmapped countries) — porting the ENGINE would
mean a hard runtime dependency on another project's server being up, which
defeats the point of a standalone audit tool. What's ported here is the
DATA layer: the same jurisdiction config files, read directly, with the
same country/subdivision -> jurisdiction mapping logic
(derive_jurisdiction_ids) reproduced for the countries covered. Education-
specific jurisdictions (FERPA, COPPA) were intentionally left out of this
port — not relevant to a general international-expansion audit.

Lets the privacy check reason about WHICH regulations plausibly apply to a
page based on its detected REGION (not just "is this in English or not"),
and check for regulation-specific signals (a GDPR-style consent mechanism,
a CCPA-style opt-out link, ...) instead of a single generic "privacy
policy found."
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

_DATA_DIR = Path(__file__).parent / "data" / "jurisdictions"

# EU member states (ISO 3166-1 alpha-2) — all map to the single gdpr_eu.json
# entry, same as peripateticware's EU_COUNTRIES set.
EU_COUNTRIES = frozenset([
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT",
    "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE",
])

# country_code -> jurisdiction data file stem. Mirrors
# privacy_jurisdiction_resolver.derive_jurisdiction_ids()'s baseline map.
# "US" -> ccpa_california is a deliberate simplification: a page-level
# crawl can reliably detect COUNTRY (via URL path or <html lang>), not
# state/province — CCPA is genuinely California-specific, so its finding
# text carries that caveat rather than claiming a firm state-level match.
_COUNTRY_TO_JURISDICTION: Dict[str, str] = {
    **{cc: "gdpr_eu" for cc in EU_COUNTRIES},
    "GB": "gdpr_eu",  # UK GDPR is substantively the same regime post-Brexit; the source engine treats it the same way
    "US": "ccpa_california",
    "BR": "lgpd_brazil",
    "CA": "pipeda_canada",
    "SG": "pdpa_singapore",
    "MX": "lpdc_mx",
    "AR": "aepd_ar",
    "ZA": "popia_za",
    "AU": "privacy_act_au",
}

# The ported files' own "requirements"/"warnings" arrays are calibrated for
# peripateticware's education/student-data domain (e.g. GDPR's top bullet
# there is "Obtain explicit parental consent before any data collection")
# — accurate for that product, wrong framing for a general commercial-site
# audit. These general-business summaries are used in findings instead;
# metadata (name, description, effective_date) still comes straight from
# the ported files. Response-day figures are only stated where they're
# well-established/safe to cite (GDPR Art. 12(3): 30 days; CCPA Cal. Civ.
# Code 1798.130: 45 days) — omitted elsewhere rather than guessed.
#
# Keyed by jurisdiction_id, NOT the "framework" field — aepd_ar.json and
# pdpa_singapore.json both carry framework="pdpa" in the source data (a
# real collision there), but jurisdiction_id is guaranteed unique per file.
_GENERAL_BUSINESS_SUMMARY = {
    "gdpr_eu": "Requires a lawful basis for processing, a clear privacy notice, consent for non-essential cookies/tracking, and support for data-subject rights (access, erasure, portability) within 30 days.",
    "ccpa_california": "Requires a privacy policy disclosing data practices, a \"Do Not Sell or Share My Personal Information\" mechanism, and response to consumer access/deletion requests within 45 days.",
    "lgpd_brazil": "Requires a lawful basis for processing, a privacy notice, and support for data-subject rights (access, correction, deletion, portability) similar to GDPR.",
    "pipeda_canada": "Requires meaningful consent for collection/use/disclosure of personal information and a designated privacy contact.",
    "pdpa_singapore": "Requires consent for collection/use/disclosure of personal data, a data protection officer, and a data-breach notification process.",
    "popia_za": "Requires a lawful basis for processing, an information officer, and support for data-subject access/correction rights.",
    "privacy_act_au": "Requires a clear APP Privacy Policy, notification at the point of collection, and reasonable steps to protect personal information (Australian Privacy Principles).",
    "lpdc_mx": "Requires a published \"aviso de privacidad\" (privacy notice) and support for ARCO rights (access, rectification, cancellation, opposition).",
    "aepd_ar": "Requires registration of the relevant database with the AAIP and support for data-subject access/rectification/deletion rights under Ley 25.326.",
}

_jurisdiction_cache: Dict[str, Optional[dict]] = {}


def _load_jurisdiction(stem: str) -> Optional[dict]:
    if stem not in _jurisdiction_cache:
        path = _DATA_DIR / f"{stem}.json"
        _jurisdiction_cache[stem] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    return _jurisdiction_cache[stem]


# Languages unambiguous enough to default to one region when a locale tag
# carries no explicit region subtag. Deliberately short — most languages
# (en, fr, es, pt, ar, de...) span multiple jurisdictions with materially
# different laws, so guessing would misinform a client.
_DEFAULT_REGION_FOR_LANGUAGE = {"ja": "JP", "ko": "KR", "zh": "CN", "hi": "IN"}


def region_from_locale_tag(tag: Optional[str]) -> Optional[str]:
    """"en-GB" -> "GB"; "pt-br" -> "BR"; "ja" -> "JP" (defaulted); "fr" -> None."""
    if not tag:
        return None
    parts = tag.replace("_", "-").split("-")
    if len(parts) >= 2 and len(parts[1]) == 2:
        return parts[1].upper()
    return _DEFAULT_REGION_FOR_LANGUAGE.get(parts[0].lower())


def jurisdictions_for_region(region: Optional[str]) -> List[dict]:
    """Full jurisdiction record(s) — display name, requirements, warnings,
    response-day obligations — for a region, straight from the ported
    reference data. Empty list if the region maps to nothing we have data
    for (most countries outside this ~9-jurisdiction set — the source
    engine covers the gap via a live DB catalog + AI discovery pipeline
    this port deliberately doesn't replicate)."""
    if not region:
        return []
    stem = _COUNTRY_TO_JURISDICTION.get(region.upper())
    if not stem:
        return []
    data = _load_jurisdiction(stem)
    return [data] if data else []


def regulations_for_region(region: Optional[str]) -> List[str]:
    """Short display-name list — the shape mixed_locale/privacy findings
    already expect."""
    names = []
    for j in jurisdictions_for_region(region):
        name = j.get("jurisdiction_name") or j.get("name") or j.get("framework", "").upper()
        if j.get("jurisdiction_id") == "ccpa_california" and region != "US-CA":
            name += " (California-specific — applies if the business serves CA residents)"
        names.append(name)
    return names


def regulation_summaries_for_region(region: Optional[str]) -> List[str]:
    """General-business one-line summary per applicable jurisdiction — see
    _GENERAL_BUSINESS_SUMMARY's note on why this is used instead of the
    ported files' own requirements/warnings arrays."""
    return [
        _GENERAL_BUSINESS_SUMMARY[j["jurisdiction_id"]]
        for j in jurisdictions_for_region(region)
        if j.get("jurisdiction_id") in _GENERAL_BUSINESS_SUMMARY
    ]


def requires_cookie_consent(region: Optional[str]) -> bool:
    """True for GDPR/LGPD-style opt-IN consent regimes only. Deliberately
    NOT keyed off compliance_checks key overlap — CCPA's compliance_checks
    also has an "opt_out_mechanism" entry, but that's an opt-OUT link
    (requires_opt_out_link, below), a materially different mechanism from a
    GDPR-style cookie-consent banner. Conflating the two produced two
    confusing findings on the same US page (a "missing cookie banner" AND
    a "missing Do Not Sell link") for what's really one requirement."""
    return any(j.get("jurisdiction_id") in ("gdpr_eu", "lgpd_brazil") for j in jurisdictions_for_region(region))


def requires_opt_out_link(region: Optional[str]) -> bool:
    """True if the region's jurisdiction requires a "Do Not Sell/Share My
    Personal Information" (or equivalent opt-out) link — CCPA's
    signature requirement, checked via its compliance_checks/consumer_rights."""
    for j in jurisdictions_for_region(region):
        if j.get("framework") == "ccpa":
            return True
        rights = j.get("consumer_rights", {})
        if "right_to_opt_out" in rights:
            return True
    return False
