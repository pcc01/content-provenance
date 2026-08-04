"""
Phase 10 — a human reviewer proposes their own translation for a segment
(the "final revision pass" workflow: type a draft right on the live page,
someone confirms before it goes live). Reuses the existing human-in-the-loop
mechanism (Phase 3's RedriveRun/RedriveRunItem with PENDING_APPROVAL)
instead of a parallel approval path — a human-authored proposal is just
another row in the same Redrive Console, approved/rejected through the
exact same RedriveEngine.approve_item/reject_item unchanged.
"""

from datetime import datetime

from app.core.database import get_db
from app.models.schemas import RedriveOutcome, RedriveRun, RedriveRunItem, RedriveRunStatus


async def propose_human_translation(
    unit_id: str, proposed_text: str, proposed_by: str,
) -> RedriveRunItem:
    db = get_db()
    unit = await db.get_translation_unit(unit_id)
    if unit is None:
        raise ValueError(f"Translation unit {unit_id} not found")

    latest_score = await db.get_latest_quality_score(unit_id)
    before_score = latest_score.score if latest_score else None
    now = datetime.utcnow()

    run = RedriveRun(
        status=RedriveRunStatus.COMPLETED,
        threshold=0,  # not used — this run never scores/thresholds anything
        scope={"unit_ids": [unit_id]},
        scoring_provider="human", redrive_provider="human",
        require_human_approval=True, triggered_by=proposed_by,
        started_at=now, finished_at=now,
        summary={"total": 1, "pending_approval": 1},
    )
    await db.create_redrive_run(run)

    item = RedriveRunItem(
        run_id=run.id, unit_id=unit_id, before_score=before_score, after_score=None,
        outcome=RedriveOutcome.PENDING_APPROVAL, proposed_text=proposed_text,
        detail=f"proposed by {proposed_by} — human draft, awaiting approval",
    )
    await db.add_redrive_run_item(item)
    return item
