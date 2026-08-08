"""Phase 14 — Vendor/Agent Scorecard API.

GET /api/v1/vendors/scorecard              - ranked JSON scorecard
GET /api/v1/vendors/scorecard/report.pdf   - branded PDF download
"""

from typing import Optional

from fastapi import APIRouter, Query, Response

from app.core.database import get_db
from app.core.vendors.report import generate_vendor_scorecard_pdf
from app.models.schemas import VendorScorecardEntry

router = APIRouter()


@router.get("/scorecard", response_model=list[VendorScorecardEntry])
async def get_vendor_scorecard(target_language: Optional[str] = Query(None)):
    """Every organization (vendor or AI agent) with at least one scored
    TranslationUnit, ranked best-first by average quality score. See
    app/core/db/repository.py's get_vendor_scorecard for the "latest score
    per unit" aggregation rule."""
    db = get_db()
    return await db.get_vendor_scorecard(target_language=target_language)


@router.get("/scorecard/report.pdf")
async def get_vendor_scorecard_pdf(target_language: Optional[str] = Query(None)):
    db = get_db()
    entries = await db.get_vendor_scorecard(target_language=target_language)
    pdf_bytes = generate_vendor_scorecard_pdf(entries, target_language=target_language)
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="vendor-scorecard.pdf"'},
    )
