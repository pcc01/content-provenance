"""
RedriveEngine — the "threshold" + "redrive" half of threshold-quality
redrive: score everything in a run's scope (skipping nothing — every unit
gets re-scored against its CURRENT version each run, since content can
silently drift below acceptable quality between runs even without an edit),
then redrive whatever scores below `threshold` through the configured
translation backend, writing a new version and rebuilding provenance.
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.database import get_db
from app.core.graph.builder import record_unit_style_context
from app.core.graph.retrieval import retrieve_style_context
from app.core.prov_builder import build_provenance_record
from app.core.redrive.ledger import UsageLedger
from app.core.scoring.automatic.meteor import compute_meteor
from app.core.scoring import licensing
from app.core.scoring.base import QualityScorer, ScoreResult
from app.core.scoring.factory import get_scorer
from app.core.scoring.style_factory import score_unit_style
from app.core.translation_backends import TranslationBackend, get_translation_backend
from app.models.schemas import (
    AutomaticMetricScore,
    QualityReport,
    QualityReportBucket,
    QualityReportItem,
    QualityReportStatus,
    QualityScore,
    RecommendedAction,
    RedriveOutcome,
    RedriveRouting,
    RedriveRun,
    RedriveRunItem,
    RedriveRunStatus,
    RoutingTarget,
    StyleAdherenceScore,
    TranslationUnit,
)


def _resolve_routing_target(routing: RedriveRouting, item: QualityReportItem) -> RoutingTarget:
    """Layered merge, later layers win: the item's own default action, then
    routing.default, then the per-bucket rule, then a reviewer's persisted
    per-unit route_override (action only), then an explicit per-unit entry in
    this redrive request. A layer leaving provider/model None keeps whatever
    an earlier layer set, so an override can change just the action."""
    action = item.recommended_action
    provider: Optional[str] = None
    model: Optional[str] = None
    review_venue: Optional[str] = None
    layers = [
        routing.default,
        routing.by_bucket.get(item.bucket.value),
        RoutingTarget(action=item.route_override) if item.route_override is not None else None,
        routing.by_unit.get(item.unit_id),
    ]
    for layer in layers:
        if layer is None:
            continue
        action = layer.action
        if layer.provider is not None:
            provider = layer.provider
        if layer.model is not None:
            model = layer.model
        if layer.review_venue is not None:
            review_venue = layer.review_venue
    return RoutingTarget(action=action, provider=provider, model=model, review_venue=review_venue)


def _classify_bucket(
    score: Optional[float], hard_fail: bool, needs_review: bool,
    style_score: Optional[float], quality_threshold: float, style_threshold: Optional[float],
) -> tuple:
    """(bucket, default recommended_action) for one evaluated unit. Order
    matters: an unscoreable unit or a critical error always outranks the
    numeric-threshold comparison — same precedence RedriveEngine.run()
    already applies (hard_fail is an independent trigger)."""
    if needs_review or score is None:
        return QualityReportBucket.NEEDS_REVIEW, RecommendedAction.HUMAN
    if hard_fail:
        return QualityReportBucket.HARD_FAIL, RecommendedAction.HUMAN
    if score < quality_threshold:
        return QualityReportBucket.BELOW_QUALITY, RecommendedAction.MT
    if style_threshold is not None and style_score is not None and style_score < style_threshold:
        return QualityReportBucket.BELOW_STYLE, RecommendedAction.MT
    return QualityReportBucket.PASS, RecommendedAction.NONE


def _below_threshold(score: Optional[float], threshold: Optional[float]) -> bool:
    return score is not None and threshold is not None and score < threshold


def _provider_label(backend: TranslationBackend) -> str:
    return backend.__class__.__name__.replace("TranslationBackend", "").lower() or "unknown"


_ENGINE_IN_DETAIL_RE = re.compile(r"\bvia (\S+) \(bucket=")


def _engine_label_from_detail(detail: Optional[str]) -> Optional[str]:
    """Pull the drafting engine out of a report-gated PENDING_APPROVAL item's
    detail string (`proposed via <label> (bucket=...)`), so approving it keeps
    the provenance trail pointing at the engine that actually produced the
    text — not the run's default."""
    if not detail:
        return None
    m = _ENGINE_IN_DETAIL_RE.search(detail)
    return m.group(1) if m else None


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
        style_scorer=None,
    ):
        self.scorer = scorer or get_scorer()
        self.scorer_label = scorer_label
        self.redrive_backend = redrive_backend or get_translation_backend()
        # None (the default) means _score_unit_style uses whatever
        # get_style_scorer() resolves to at call time — same lazy-default
        # pattern as `scorer` above. Overriding it (as tests do) avoids
        # needing real ANTHROPIC_API_KEY credentials for style_threshold
        # coverage, mirroring how `scorer` is already injectable.
        self.style_scorer = style_scorer
        # An explicit label always wins over one derived from the backend —
        # approving/rejecting an item belonging to an existing RedriveRun
        # should use THAT run's own recorded redrive_provider, not whatever
        # TRANSLATION_PROVIDER happens to be configured right now (which may
        # have changed since the run was created, and is never "human" for
        # a human-authored proposal — see app/core/redrive/propose.py).
        self.redrive_label = redrive_label or _provider_label(self.redrive_backend)
        self.ledger = UsageLedger()
        # Phase 3 — report-gated redrive can send different units to different
        # engines; build each provider/model backend once per run.
        self._backend_cache: Dict[tuple, TranslationBackend] = {}

    def _backend_for(self, provider: Optional[str], model: Optional[str]):
        """(backend, label) for a routing target. None provider -> the run's
        default redrive backend."""
        if not provider:
            return self.redrive_backend, self.redrive_label
        key = (provider.lower(), model or "")
        if key not in self._backend_cache:
            self._backend_cache[key] = get_translation_backend(provider, model)
        return self._backend_cache[key], provider.lower()

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
            hard_fail=result.hard_fail,
        )
        return await db.save_quality_score(record)

    async def preview(
        self, scope: Dict[str, Any], threshold: float,
        style_threshold: Optional[float] = None, style_guide_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Dry-run forecast: scores everything in scope (writing real
        QualityScore rows — scoring itself is free/side-effect-safe to
        repeat) and reports how many units would be redriven at this
        threshold, mirroring peripateticware's cutoff-preview table, without
        spending any translation budget. style_threshold, when given, adds
        the Phase 13 style-adherence axis to the same forecast."""
        db = get_db()
        units = await db.list_units_by_scope(scope)
        below = below_style = 0
        total_chars = 0
        for unit in units:
            score_record = await self._score_unit(unit)
            quality_below = _below_threshold(score_record.score, threshold)
            style_below = False
            if style_threshold is not None:
                style_record = await self._score_unit_style(unit, style_guide_id)
                style_below = _below_threshold(style_record.overall_score, style_threshold)
                if style_below:
                    below_style += 1
            if quality_below:
                below += 1
            if quality_below or style_below:
                total_chars += len(unit.source_text)
        result = {
            "scope_count": len(units),
            "below_threshold": below,
            "estimated_source_chars": total_chars,
            "redrive_provider": self.redrive_label,
        }
        if style_threshold is not None:
            result["below_style_threshold"] = below_style
        return result

    async def evaluate(
        self, scope: Dict[str, Any], quality_threshold: float,
        style_threshold: Optional[float] = None, style_guide_id: Optional[str] = None,
        scoring_model: Optional[str] = None, reference_mode: Optional[str] = None,
        triggered_by: Optional[str] = None,
    ) -> QualityReport:
        """The "produce a report" step: score everything in scope (writing
        real QualityScore rows — free and side-effect-safe to repeat),
        bucket each unit, and persist an exportable QualityReport. Spends no
        translation budget; Phase 3's redrive_from_report() consumes the
        result instead of re-scoring. Same scoring loop as preview(), but
        persisted per-unit with a bucket + a default routing recommendation."""
        db = get_db()
        report = QualityReport(
            scope=scope, quality_threshold=quality_threshold, style_threshold=style_threshold,
            style_guide_id=style_guide_id, scoring_provider=self.scorer_label,
            scoring_model=scoring_model, reference_mode=reference_mode, triggered_by=triggered_by,
            status=QualityReportStatus.RUNNING,
        )
        await db.create_quality_report(report)

        units = await db.list_units_by_scope(scope)
        bucket_counts = {b.value: 0 for b in QualityReportBucket}
        est_chars = safe_n = noncomm_n = unknown_n = 0

        for unit in units:
            score_record = await self._score_unit(unit)
            style_score: Optional[float] = None
            if style_threshold is not None:
                style_record = await self._score_unit_style(unit, style_guide_id)
                style_score = style_record.overall_score

            bucket, action = _classify_bucket(
                score_record.score, score_record.hard_fail, score_record.needs_review,
                style_score, quality_threshold, style_threshold,
            )
            safe = licensing.commercial_safe(score_record.scorer)
            await db.add_quality_report_item(QualityReportItem(
                report_id=report.id, unit_id=unit.id, quality_score_id=score_record.id,
                scorer=score_record.scorer, before_score=score_record.score, style_score=style_score,
                reasons=list(score_record.reasons), errors=list(score_record.errors),
                hard_fail=score_record.hard_fail, needs_review=score_record.needs_review,
                bucket=bucket, recommended_action=action, commercial_safe=safe,
                source_text_len=len(unit.source_text or ""),
            ))

            bucket_counts[bucket.value] += 1
            if bucket != QualityReportBucket.PASS:
                est_chars += len(unit.source_text or "")
            if safe is True:
                safe_n += 1
            elif safe is False:
                noncomm_n += 1
            else:
                unknown_n += 1

        totals = {
            "units": len(units),
            "below_threshold": bucket_counts[QualityReportBucket.BELOW_QUALITY.value]
            + bucket_counts[QualityReportBucket.HARD_FAIL.value],
            "hard_fail": bucket_counts[QualityReportBucket.HARD_FAIL.value],
            "needs_review": bucket_counts[QualityReportBucket.NEEDS_REVIEW.value],
            "below_style": bucket_counts[QualityReportBucket.BELOW_STYLE.value],
            "est_source_chars": est_chars,
            "commercial_safe": safe_n,
            "non_commercial": noncomm_n,
            "commercial_unknown": unknown_n,
        }
        await db.update_quality_report(
            report.id, status=QualityReportStatus.COMPLETED,
            finished_at=datetime.utcnow(), summary=bucket_counts, totals=totals,
        )
        return await db.get_quality_report(report.id)

    async def _score_unit_style(
        self, unit: TranslationUnit, style_guide_id: Optional[str],
    ) -> StyleAdherenceScore:
        return await score_unit_style(unit, style_guide_id=style_guide_id, scorer=self.style_scorer)

    async def _apply_redrive(
        self, unit: TranslationUnit, new_text: str, confidence: Optional[float],
        before_score: Optional[float], reasons_label: str, approved_by: Optional[str] = None,
        style_guide_id: Optional[str] = None, engine_label: Optional[str] = None,
    ) -> QualityScore:
        """Writes a redrive to the unit — new version, provenance rebuild,
        stale-cache invalidation, re-score. Shared by the immediate-apply
        path in run() and the human-in-the-loop approve_item() below, so
        "approved later" and "applied immediately" behave identically once
        the text is actually going live. style_guide_id, when given, also
        re-scores style adherence on the new text so
        get_latest_style_adherence_score/provenance reflect the redriven
        version, not the one it replaced. engine_label overrides
        self.redrive_label in the version note — Phase 3's report-gated
        redrive sends different units to different engines in one run, so the
        provenance trail must name the one that actually did THIS unit."""
        db = get_db()
        previous_text = unit.target_text
        unit.target_text = new_text
        unit.confidence_score = confidence
        note = f"Redriven via {engine_label or self.redrive_label}: previous score {before_score} ({reasons_label})"
        if approved_by:
            note += f" — approved by {approved_by}"
        await db.save_translation_unit(unit, version_source_event="redrive", version_note=note)

        if style_guide_id is not None:
            await self._score_unit_style(unit, style_guide_id)

        if previous_text:
            await self._record_meteor_regression(unit, new_text, previous_text)

        deps = await db.get_deployments_for_unit(unit.id)
        prov_record = await build_provenance_record(unit, deps)
        await db.save_provenance_record(prov_record)
        await db.delete_xliff(unit.id)  # cached export is now stale

        return await self._score_unit(unit)

    async def _record_meteor_regression(
        self, unit: TranslationUnit, new_text: str, previous_text: str,
    ) -> None:
        """Phase 15 — how lexically similar is the new candidate to the
        version it's replacing, using the prior approved text as a
        pseudo-reference (see app/core/scoring/automatic/meteor.py).
        Purely informational: never blocks or reverses a redrive, just
        records a corroborating signal alongside the LLM-judge score."""
        db = get_db()
        score = await compute_meteor(new_text, previous_text)
        if score is None:
            return  # nltk not installed — degrade silently, same as embed_text
        versions = await db.list_translation_unit_versions(unit.id)
        reference_version_id = versions[-2].id if len(versions) >= 2 else None
        await db.save_automatic_metric_score(AutomaticMetricScore(
            unit_id=unit.id, metric="meteor", score=score, raw_score=score / 100,
            reference_type="previous_version", reference_unit_version_id=reference_version_id,
        ))

    async def run(self, run: RedriveRun) -> RedriveRun:
        db = get_db()
        await db.update_redrive_run(run.id, status=RedriveRunStatus.RUNNING)

        units = await db.list_units_by_scope(run.scope)
        redriven = skipped = failed = no_budget = pending_approval = 0

        for unit in units:
            score_record = await self._score_unit(unit)
            before_score = score_record.score
            # Phase 15 — hard_fail (MQM's "any critical error -> automatic
            # Fail" rule) redrives a unit even if its numeric score is
            # still above `threshold` — see QualityScore.hard_fail's
            # docstring (app/models/schemas.py) for why the two are kept
            # independent rather than folded into one condition.
            quality_below = _below_threshold(score_record.score, run.threshold) or score_record.hard_fail

            # Phase 13 — a second, independent threshold axis: style score
            # below run.style_threshold also triggers a redrive, even when
            # quality alone would have passed. See RedriveRun.style_threshold's
            # docstring for why this is opt-in (None = scored but never
            # itself the reason for a redrive).
            style_reasons: List[str] = []
            style_below = False
            if run.style_threshold is not None:
                style_record = await self._score_unit_style(unit, run.style_guide_id)
                style_below = _below_threshold(style_record.overall_score, run.style_threshold)
                style_reasons = [f"style:{r}" for r in style_record.reasons]

            if not (quality_below or style_below):
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

            style_prompt_context = None
            if run.style_guide_id is not None or settings.graph_retrieval_enabled:
                retrieval = await retrieve_style_context(
                    unit.source_text, unit.source_language, unit.target_language,
                    style_guide_id=run.style_guide_id, top_k=settings.graph_retrieval_top_k,
                )
                if not retrieval.is_empty:
                    style_prompt_context = retrieval.as_prompt_context()
                    await record_unit_style_context(unit.id, retrieval)

            try:
                new_text, confidence = await self.redrive_backend.translate(
                    unit.source_text, unit.source_language, unit.target_language,
                    style_context=style_prompt_context,
                )
            except Exception as e:
                failed += 1
                await db.add_redrive_run_item(RedriveRunItem(
                    run_id=run.id, unit_id=unit.id, before_score=before_score,
                    after_score=before_score, outcome=RedriveOutcome.FAILED, detail=str(e),
                ))
                continue

            await self.ledger.record(self.redrive_label, char_count)  # the translate() call already happened
            hard_fail_reason = ["hard_fail:critical_error"] if score_record.hard_fail else []
            reasons_label = ",".join(list(score_record.reasons) + hard_fail_reason + style_reasons) or "low score"

            if run.require_human_approval:
                pending_approval += 1
                await db.add_redrive_run_item(RedriveRunItem(
                    run_id=run.id, unit_id=unit.id, before_score=before_score, after_score=None,
                    outcome=RedriveOutcome.PENDING_APPROVAL, proposed_text=new_text,
                    detail=f"proposed via {self.redrive_label} — awaiting human approval",
                ))
                continue

            after_score_record = await self._apply_redrive(
                unit, new_text, confidence, before_score, reasons_label,
                style_guide_id=run.style_guide_id if run.style_threshold is not None else None,
            )
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

    async def _retrieve_style_context(self, unit: TranslationUnit, style_guide_id: Optional[str]) -> Optional[str]:
        if style_guide_id is None and not settings.graph_retrieval_enabled:
            return None
        retrieval = await retrieve_style_context(
            unit.source_text, unit.source_language, unit.target_language,
            style_guide_id=style_guide_id, top_k=settings.graph_retrieval_top_k,
        )
        if retrieval.is_empty:
            return None
        await record_unit_style_context(unit.id, retrieval)
        return retrieval.as_prompt_context()

    async def _candidate_passes(
        self, unit: TranslationUnit, candidate_text: str, threshold: float,
    ) -> tuple:
        """Phase 4 — score an mt candidate BEFORE applying it, with the same
        judge the report used. Returns (passes, reason). `passes` is False on
        an unscoreable candidate, a hard fail, or a score under the report's
        threshold — those get held for a human instead of going live."""
        probe = unit.model_copy(update={"target_text": candidate_text})
        try:
            result = await self.scorer.score(probe)
        except Exception as e:  # same resilience contract as _score_unit
            return False, f"second-pass score failed ({e})"
        if result.score is None:
            return False, "second-pass score: unscoreable"
        if result.hard_fail:
            return False, f"second-pass score {result.score:.0f} with a critical error"
        if result.score < threshold:
            return False, f"second-pass score {result.score:.0f} < {threshold:.0f}"
        return True, f"second-pass score {result.score:.0f}"

    async def _send_to_tms(self, unit, item, draft_text: str, backend_label: str) -> tuple:
        """A `human` route with review_venue="crowdin" — push the string +
        MT draft + quality note to the TMS instead of the in-app queue.
        Falls back to PENDING_APPROVAL if the TMS is unconfigured / errors,
        so a misconfiguration never fails the whole run."""
        from app.core import tms_service  # local import: engine has no TMS dep otherwise

        fallback = (
            RedriveOutcome.PENDING_APPROVAL,
            f"proposed via {backend_label} (bucket={item.bucket.value}) — awaiting human approval",
        )
        note = (
            f"score {item.before_score}; "
            f"{', '.join(item.reasons) or 'bucket:' + item.bucket.value}; "
            f"flagged by {self.scorer_label} — via Content Provenance"
        )
        try:
            res = await tms_service.send_unit_for_review(
                unit.id, mt_draft=draft_text, quality_note=note,
            )
        except (ValueError, LookupError) as e:
            return (fallback[0], f"{fallback[1]} (TMS unavailable: {e})")
        return (
            RedriveOutcome.SENT_TO_TMS,
            f"sent to {res['provider']} string {res['string_id']} for human review "
            f"(bucket={item.bucket.value})",
        )

    async def redrive_from_report(
        self, report: QualityReport, routing: Optional[RedriveRouting] = None,
        triggered_by: Optional[str] = None, second_review: bool = False,
    ) -> RedriveRun:
        """Phase 3/4 — consume a saved QualityReport instead of re-scoring a
        scope. Each report item is routed (none -> left alone, mt -> applied,
        human -> proposed as PENDING_APPROVAL) to an engine resolved per
        bucket / per unit.

        Phase 4 second-pass gate for an mt route: the candidate is scored
        before it goes live. It's applied only if it clears the report's
        threshold (and `second_review` is off); otherwise it's held as
        PENDING_APPROVAL with the reason, so a failed retranslation never
        silently replaces the previous version."""
        db = get_db()
        routing = routing or RedriveRouting()
        style_guide_id = report.style_guide_id
        rescore_style = report.style_threshold is not None

        run = RedriveRun(
            status=RedriveRunStatus.RUNNING,
            threshold=report.quality_threshold, style_threshold=report.style_threshold,
            style_guide_id=style_guide_id, scope=report.scope,
            scoring_provider=report.scoring_provider,
            redrive_provider=(
                routing.default.provider if routing.default and routing.default.provider
                else self.redrive_label
            ),
            triggered_by=triggered_by, from_report_id=report.id,
            routing=routing.model_dump(mode="json"), second_review=second_review,
        )
        await db.create_redrive_run(run)

        redriven = pending = skipped = failed = no_budget = 0
        for item in report.items:
            target = _resolve_routing_target(routing, item)

            if target.action == RecommendedAction.NONE:
                skipped += 1
                await db.add_redrive_run_item(RedriveRunItem(
                    run_id=run.id, unit_id=item.unit_id, before_score=item.before_score,
                    after_score=item.before_score, outcome=RedriveOutcome.SKIPPED_ABOVE_THRESHOLD,
                    detail=f"bucket={item.bucket.value}, action=none",
                ))
                continue

            unit = await db.get_translation_unit(item.unit_id)
            if unit is None:
                failed += 1
                await db.add_redrive_run_item(RedriveRunItem(
                    run_id=run.id, unit_id=item.unit_id, before_score=item.before_score,
                    after_score=None, outcome=RedriveOutcome.FAILED, detail="translation unit not found",
                ))
                continue

            backend, backend_label = self._backend_for(target.provider, target.model)
            char_count = len(unit.source_text or "")
            if not await self.ledger.can_spend(backend_label, char_count):
                no_budget += 1
                await db.add_redrive_run_item(RedriveRunItem(
                    run_id=run.id, unit_id=unit.id, before_score=item.before_score,
                    after_score=item.before_score, outcome=RedriveOutcome.NO_BUDGET,
                    detail=f"{backend_label} usage budget exhausted",
                ))
                continue

            style_prompt_context = await self._retrieve_style_context(unit, style_guide_id)
            try:
                new_text, confidence = await backend.translate(
                    unit.source_text, unit.source_language, unit.target_language,
                    style_context=style_prompt_context,
                )
            except Exception as e:
                failed += 1
                await db.add_redrive_run_item(RedriveRunItem(
                    run_id=run.id, unit_id=unit.id, before_score=item.before_score,
                    after_score=None, outcome=RedriveOutcome.FAILED, detail=str(e),
                ))
                continue

            await self.ledger.record(backend_label, char_count)
            reasons_label = ",".join(item.reasons) or f"bucket:{item.bucket.value}"

            if target.action == RecommendedAction.HUMAN:
                pending += 1
                if target.review_venue == "crowdin":
                    outcome, detail = await self._send_to_tms(unit, item, new_text, backend_label)
                else:
                    outcome, detail = (
                        RedriveOutcome.PENDING_APPROVAL,
                        f"proposed via {backend_label} (bucket={item.bucket.value}) — awaiting human approval",
                    )
                await db.add_redrive_run_item(RedriveRunItem(
                    run_id=run.id, unit_id=unit.id, before_score=item.before_score, after_score=None,
                    outcome=outcome, proposed_text=new_text, detail=detail,
                ))
                continue

            # mt route — Phase 4: gate the candidate before it goes live.
            passes, why = await self._candidate_passes(unit, new_text, report.quality_threshold)
            if second_review or not passes:
                pending += 1
                held = "second-review requested" if (second_review and passes) else why
                await db.add_redrive_run_item(RedriveRunItem(
                    run_id=run.id, unit_id=unit.id, before_score=item.before_score, after_score=None,
                    outcome=RedriveOutcome.PENDING_APPROVAL, proposed_text=new_text,
                    detail=f"mt candidate via {backend_label} (bucket={item.bucket.value}) — {held} — awaiting human approval",
                ))
                continue

            after = await self._apply_redrive(
                unit, new_text, confidence, item.before_score, reasons_label,
                style_guide_id=style_guide_id if rescore_style else None,
                engine_label=backend_label,
            )
            redriven += 1
            await db.add_redrive_run_item(RedriveRunItem(
                run_id=run.id, unit_id=unit.id, before_score=item.before_score,
                after_score=after.score, outcome=RedriveOutcome.REDRIVEN,
                detail=f"redriven via {backend_label} (bucket={item.bucket.value}) — {why}",
            ))

        summary = {
            "total": len(report.items), "redriven": redriven, "pending_approval": pending,
            "skipped_above_threshold": skipped, "failed": failed, "no_budget": no_budget,
            "from_report_id": report.id,
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

        run = await db.get_redrive_run(item.run_id)
        style_guide_id = run.style_guide_id if run and run.style_threshold is not None else None

        # A report-gated item's proposed_text may have been drafted by a
        # per-bucket engine, not the run default — keep that in the version
        # note and in the item's own trail.
        drafting_engine = _engine_label_from_detail(item.detail)

        after_score_record = await self._apply_redrive(
            unit, item.proposed_text, unit.confidence_score, item.before_score,
            reasons_label="approved redrive", approved_by=approved_by, style_guide_id=style_guide_id,
            engine_label=drafting_engine,
        )
        detail = f"approved by {approved_by}"
        if drafting_engine:
            detail += f" (drafted via {drafting_engine})"
        updated = await db.update_redrive_run_item(
            item_id, outcome=RedriveOutcome.REDRIVEN, after_score=after_score_record.score,
            detail=detail, approved_by=approved_by, approved_at=datetime.utcnow(),
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
