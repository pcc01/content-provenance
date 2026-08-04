"""
Phase 9 — page history / time-travel. Reconstructs a page as it looked at a
past point in time, diffs two points, and lists a page's timeline. No new
snapshot-storage system: TranslationUnitVersion (Phase 2) is already an
append-only, timestamped commit log per segment — this module just queries
it point-in-time against the structural template Phase 8 already captures
in PageSnapshot.
"""

import html as html_lib
import re
from datetime import datetime
from typing import Dict, List, Optional

from app.core.database import get_db
from app.models.schemas import TranslationUnitVersion


def _version_as_of(
    versions: List[TranslationUnitVersion], as_of: datetime,
) -> Optional[TranslationUnitVersion]:
    candidates = [v for v in versions if v.created_at <= as_of]
    if not candidates:
        return None
    return max(candidates, key=lambda v: v.created_at)


def _substitute_text(html_doc: str, unit_id: str, text: str) -> str:
    """Every harvested element is a leaf (no nested elements — Phase 8's
    isHarvestable() guarantees that), so everything between a data-tu-id
    tag's '>' and the next '<' is safe to swap wholesale. Not a
    general-purpose HTML rewriter — only correct for HTML this system
    generated itself."""
    pattern = re.compile(r'(data-tu-id="' + re.escape(unit_id) + r'"[^>]*>)([^<]*)(<)')
    escaped = html_lib.escape(text)
    return pattern.sub(lambda m: m.group(1) + escaped + m.group(3), html_doc, count=1)


async def get_page_timeline(url: str, target_language: str) -> Optional[List[datetime]]:
    """None means no snapshot exists at all for this url+locale (never
    fetched) — distinct from an empty list, which can't actually happen
    once a snapshot exists (the initial fetch always writes at least one
    version per harvested unit)."""
    db = get_db()
    snapshot = await db.get_latest_page_snapshot(url, target_language)
    if snapshot is None:
        return None
    return await db.list_version_timestamps(snapshot.harvested_unit_ids)


async def reconstruct_page_as_of(url: str, target_language: str, as_of: datetime) -> Optional[str]:
    db = get_db()
    snapshots = await db.list_page_snapshots(url, target_language)  # ascending by fetched_at
    template = None
    for snap in snapshots:
        if snap.fetched_at <= as_of:
            template = snap
    if template is None:
        return None

    versions_by_unit = await db.list_translation_unit_versions_for_units(template.harvested_unit_ids)
    html_doc = template.html
    for unit_id, versions in versions_by_unit.items():
        version = _version_as_of(versions, as_of)
        if version is not None:
            html_doc = _substitute_text(html_doc, unit_id, version.target_text)
    return html_doc


async def diff_page(
    url: str, target_language: str, from_ts: datetime, to_ts: datetime,
) -> Optional[List[Dict]]:
    db = get_db()
    snapshot = await db.get_latest_page_snapshot(url, target_language)
    if snapshot is None:
        return None

    versions_by_unit = await db.list_translation_unit_versions_for_units(snapshot.harvested_unit_ids)
    changes = []
    for unit_id, versions in versions_by_unit.items():
        before = _version_as_of(versions, from_ts)
        after = _version_as_of(versions, to_ts)
        before_text = before.target_text if before else None
        after_text = after.target_text if after else None
        if before_text != after_text:
            unit = await db.get_translation_unit(unit_id)
            changes.append({
                "unit_id": unit_id,
                "source_text": unit.source_text if unit else None,
                "before_text": before_text,
                "after_text": after_text,
            })
    return changes
