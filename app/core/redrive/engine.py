"""
RedriveEngine — the "threshold" + "redrive" half of threshold-quality
redrive: score everything in a run's scope (skipping nothing — every unit
gets re-scored against its CURRENT version each run, since content can
silently drift below acceptable quality between runs even without an edit),
then redrive whatever scores below `threshold` through the configured
translation backend, writing a new version and rebuilding provenance.
"""

from datetime import datetime
from typing import Any, Dict, Optional

from app.core.database import get_db
from app.core.prov_builder import build_provenance_record
from app.core.redrive.ledger import UsageLedger
from app.core.scoring.base import QualityScorer, ScoreResult
from app.core.scoring.factory import get_scorer
from app.core.translation_backends import TranslationBackend, get_translation_backend
from app.models.schemas import (
    QualityScore, RedriveOutcome, RedriveRun, RedriveRunItem, RedriveRunStatus,
    TranslationUnit,
)


def _provider_label(backend: TranslationBackend) -> str:
    return backend.__class__.__name__.replace("TranslationBackend", "").lower() or "unknown"


class _NeverInvokedScorer(QualityScorer):
    """approve_item/reject_item never call .score() — RedriveEngine still
    requires a scorer instance at construction time, and "human" (Phase
    10's proposal runs — see propose.py) isn't a real provider get_scorer()
    recognizes. This exists purely so construction succeeds; if it were
    ever actually invoked that's a bug elsewhere, so it fails loudly rather
    than returning a made-up score."""

    async def score(self, unit: TranslationUnit) -> ScoreResult:
        raise RuntimeError("_NeverInvokedScorer.score() was called — this should be unreachable.")


def build_engine_for_run(run: RedriveRun) -> "RedriveEngine":
    """Constructs an engine using a RUN's OWN recorded scoring_provider/
    redrive_provider — approving/rejecting an item must use what that run
    was actually configured with, not whatever's globally configured now
    (which may have drifted since the run was created, and is never a real
    scorer for a "human" provider)."""
    provider = run.scoring_provider.lower()
    scorer = _NeverInvokedScorer() if provider == "human" else get_scorer(provider)
    return RedriveEngine(scorer=scorer, scorer_label=provider, redrive_label=run.redrive_provider)


async def build_engine_for_item(item_id: str) -> Optional["RedriveEngine"]:
    """Same as build_engine_for_run, resolved from an item id — what the
    approve/reject endpoints and Phase 10's bulk-approve both start from.
    None if the item or its run can't be found."""
    db = get_db()
    item = await db.get_redrive_run_item(item_id)
    if item is None:
        return None
    run = await db.get_redrive_run(item.run_id)
    if run is None:
        return None
    return build_engine_for_run(run)


class RedriveEngine:
    def __init__(
        self,
        scorer: Optional[QualityScorer] = None,
        scorer_label: str = "unknown",
        redrive_backend: Optional[TranslationBackend] = None,
        redrive_label: Optional[str] = None,
    ):
        self.scorer = scorer or get_scorer()
        self.scorer_label = scorer_label
        self.redrive_backend = redrive_backend or get_translation_backend()
        # An explicit label always wins over one derived from the backend —
        # approving/rejecting an item belonging to an existing RedriveRun
        # should use THAT run's own recorded redrive_provider, not whatever
        # TRANSLATION_PROVIDER happens to be configured right now (which may
        # have changed since the run was created, and is never "human" for
        # a human-authored proposal — see app/core/redrive/propose.py).
        self.redrive_label = redrive_label or _provider_label(self.redrive_backend)
        self.ledger = UsageLedger()

    async def _score_unit(self, unit: TranslationUnit) -> QualityScore:
        db = get_db()
        try:
            result = await self.scorer.score(unit)
        except Exception as e:
            # A scorer failure (missing credentials, network error, an
            # unparseable model response that slipped past the scorer's own
            # handling) must not crash an entire batch run over one unit —
            # same resilience principle the Ollama scorer already applies to
            # its own timeouts. Falls back to needs_review instead.
            result = ScoreResult(score=None, reasons=["scorer_error"], raw_response=str(e), needs_review=True)
        scorer_name = "deterministic" if result.deterministic else self.scorer_label
        record = QualityScore(
            unit_id=unit.id, score=result.score, scorer=scorer_name,
            reasons=result.reasons, errors=result.errors,
            raw_response=result.raw_response, needs_review=result.needs_review,
        )
        return await db.save_quality_score(record)

    async def preview(self, scope: Dict[str, Any], threshold: float) -> Dict[str, Any]:
        """Dry-run forecast: scores everything in scope (writing real
        QualityScore rows — scoring itself is free/side-effect-safe to
        repeat) and reports how many units would be redriven at this
        threshold, mirroring peripateticware's cutoff-preview table, without
        spending any translation budget."""
        db = get_db()
        units = await db.list_units_by_scope(scope)
        below = 0
        total_chars = 0
        for unit in units:
            score_record = await self._score_unit(unit)
            if score_record.score is not None and score_record.score < threshold:
                below += 1
                total_chars += len(unit.source_text)
        return {
            "scope_count": len(units),
            "below_threshold": below,
            "estimated_source_chars": total_chars,
            "redrive_provider": self.redrive_label,
        }

    async def _apply_redrive(
        self, unit: TranslationUnit, new_text: str, confidence: Optional[float],
        before_score: Optional[float], reasons_label: str, approved_by: Optional[str] = None,
    ) -> QualityScore:
        """Writes a redrive to the unit — new version, provenance rebuild,
        stale-cache invalidation, re-score. Shared by the immediate-apply
        path in run() and the human-in-the-loop approve_item() below, so
        "approved later" and "applied immediately" behave identically once
        the text is actually going live."""
        db = get_db()
        unit.target_text = new_text
        unit.confidence_score = confidence
        note = f"Redriven via {self.redrive_label}: previous score {before_score} ({reasons_label})"
        if approved_by:
            note += f" — approved by {approved_by}"
        await db.save_translation_unit(unit, version_source_event="redrive", version_note=note)

        deps = await db.get_deployments_for_unit(unit.id)
        prov_record = await build_provenance_record(unit, deps)
        await db.save_provenance_record(prov_record)
        await db.delete_xliff(unit.id)  # cached export is now stale

        return await self._score_unit(unit)

    async def run(self, run: RedriveRun) -> RedriveRun:
        db = get_db()
        await db.update_redrive_run(run.id, status=RedriveRunStatus.RUNNING)

        units = await db.list_units_by_scope(run.scope)
        redriven = skipped = failed = no_budget = pending_approval = 0

        for unit in units:
            score_record = await self._score_unit(unit)
            before_score = score_record.score

            if score_record.score is None or score_record.score >= run.threshold:
                skipped += 1
                await db.add_redrive_run_item(RedriveRunItem(
                    run_id=run.id, unit_id=unit.id, before_score=before_score,
                    after_score=before_score, outcome=RedriveOutcome.SKIPPED_ABOVE_THRESHOLD,
                ))
                continue

            char_count = len(unit.source_text)
            if not await self.ledger.can_spend(self.redrive_label, char_count):
                no_budget += 1
                await db.add_redrive_run_item(RedriveRunItem(
                    run_id=run.id, unit_id=unit.id, before_score=before_score,
                    after_score=before_score, outcome=RedriveOutcome.NO_BUDGET,
                    detail=f"{self.redrive_label} usage budget exhausted",
                ))
                continue

            try:
                new_text, confidence = await self.redrive_backend.translate(
                    unit.source_text, unit.source_language, unit.target_language,
                )
            except Exception as e:
                failed += 1
                await db.add_redrive_run_item(RedriveRunItem(
                    run_id=run.id, unit_id=unit.id, before_score=before_score,
                    after_score=before_score, outcome=RedriveOutcome.FAILED, detail=str(e),
                ))
                continue

            await self.ledger.record(self.redrive_label, char_count)  # the translate() call already happened
            reasons_label = ",".join(score_record.reasons) or "low score"

            if run.require_human_approval:
                pending_approval += 1
                await db.add_redrive_run_item(RedriveRunItem(
                    run_id=run.id, unit_id=unit.id, before_score=before_score, after_score=None,
                    outcome=RedriveOutcome.PENDING_APPROVAL, proposed_text=new_text,
                    detail=f"proposed via {self.redrive_label} — awaiting human approval",
                ))
                continue

            after_score_record = await self._apply_redrive(unit, new_text, confidence, before_score, reasons_label)
            redriven += 1
            await db.add_redrive_run_item(RedriveRunItem(
                run_id=run.id, unit_id=unit.id, before_score=before_score,
                after_score=after_score_record.score, outcome=RedriveOutcome.REDRIVEN,
                detail=f"redriven via {self.redrive_label}",
            ))

        summary = {
            "total": len(units), "redriven": redriven, "skipped_above_threshold": skipped,
            "failed": failed, "no_budget": no_budget, "pending_approval": pending_approval,
        }
        await db.update_redrive_run(
            run.id, status=RedriveRunStatus.COMPLETED, finished_at=datetime.utcnow(), summary=summary,
        )
        return await db.get_redrive_run(run.id)

    async def approve_item(self, item_id: str, approved_by: str) -> RedriveRunItem:
        """Applies a PENDING_APPROVAL item's proposed_text as the unit's
        live translation."""
        db = get_db()
        item = await db.get_redrive_run_item(item_id)
        if item is None:
            raise ValueError(f"Redrive run item {item_id} not found")
        if item.outcome != RedriveOutcome.PENDING_APPROVAL:
            raise ValueError(f"Item {item_id} is not pending approval (outcome={item.outcome.value})")
        if not item.proposed_text:
            raise ValueError(f"Item {item_id} has no proposed text to approve")

        unit = await db.get_translation_unit(item.unit_id)
        if unit is None:
            raise ValueError(f"Translation unit {item.unit_id} not found")

        after_score_record = await self._apply_redrive(
            unit, item.proposed_text, unit.confidence_score, item.before_score,
            reasons_label="approved redrive", approved_by=approved_by,
        )
        updated = await db.update_redrive_run_item(
            item_id, outcome=RedriveOutcome.REDRIVEN, after_score=after_score_record.score,
            detail=f"approved by {approved_by}", approved_by=approved_by, approved_at=datetime.utcnow(),
        )
        return updated

    async def reject_item(self, item_id: str, rejected_by: str, reason: Optional[str] = None) -> RedriveRunItem:
        """Declines a PENDING_APPROVAL item — the unit is left untouched."""
        db = get_db()
        item = await db.get_redrive_run_item(item_id)
        if item is None:
            raise ValueError(f"Redrive run item {item_id} not found")
        if item.outcome != RedriveOutcome.PENDING_APPROVAL:
            raise ValueError(f"Item {item_id} is not pending approval (outcome={item.outcome.value})")

        detail = f"rejected by {rejected_by}" + (f": {reason}" if reason else "")
        updated = await db.update_redrive_run_item(
            item_id, outcome=RedriveOutcome.REJECTED, detail=detail,
            approved_by=rejected_by, approved_at=datetime.utcnow(),
        )
        return updated
