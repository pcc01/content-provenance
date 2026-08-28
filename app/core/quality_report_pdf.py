"""Phase 1 (report-gated redrive) — branded PDF for a QualityReport, the
same reportlab pattern as app/core/vendors/report.py and
app/core/audit/report.py: logo, summary block, then the per-unit issue
table worst-first. This is the "produce a report with quality issues" hand-off
a reviewer takes into the redrive step.

Every page carries a non-commercial-signal stamp when the report's score
leaned on a research-only evaluator (M-Prometheus / XCOMET / CometKiwi) —
see app/core/scoring/licensing.py.
"""

import io
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.core.scoring import licensing
from app.models.schemas import QualityReport, QualityReportItem

_LOGO_PATH = Path(__file__).parent.parent / "static" / "branding" / "logo.png"

_BUCKET_LABEL = {
    "pass": "Pass",
    "below_quality": "Below quality",
    "hard_fail": "Critical error",
    "below_style": "Below style",
    "needs_review": "Needs review",
}
_BUCKET_COLOR = {
    "pass": colors.HexColor("#2f9e44"),
    "below_quality": colors.HexColor("#f5a524"),
    "hard_fail": colors.HexColor("#e5484d"),
    "below_style": colors.HexColor("#f5a524"),
    "needs_review": colors.HexColor("#6b7280"),
}
_ACTION_LABEL = {"none": "—", "human": "Human review", "mt": "Retranslate (MT)"}


def _fmt_score(score: Optional[float]) -> str:
    return f"{score:.0f}" if score is not None else "—"


def _clip(text: str, limit: int = 90) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _stamp(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.HexColor("#9ca3af"))
    canvas.drawString(0.75 * inch, 0.5 * inch, doc._qr_footer)
    canvas.drawRightString(7.75 * inch, 0.5 * inch, f"page {doc.page}")
    canvas.restoreState()


def generate_quality_report_pdf(report: QualityReport, items: List[QualityReportItem]) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        topMargin=0.75 * inch, bottomMargin=0.75 * inch, leftMargin=0.75 * inch, rightMargin=0.75 * inch,
    )
    non_commercial = report.totals.get("non_commercial", 0) or 0
    unknown = report.totals.get("commercial_unknown", 0) or 0
    if non_commercial:
        doc._qr_footer = (
            f"CONTAINS RESEARCH / NON-COMMERCIAL SIGNALS — {non_commercial} unit(s) scored by "
            f"{report.scoring_provider} ({licensing.license_id(report.scoring_provider)}). Not for a commercial deliverable."
        )
    elif unknown:
        doc._qr_footer = f"{unknown} unit(s) scored by an unclassified local checkpoint — confirm its licence before commercial use."
    else:
        doc._qr_footer = "All scores from commercially-usable evaluators."

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("QRTitle", parent=styles["Title"], fontSize=20, spaceAfter=4)
    subtitle_style = ParagraphStyle(
        "QRSubtitle", parent=styles["Normal"], fontSize=10.5, textColor=colors.HexColor("#6b7280"),
    )
    section_style = ParagraphStyle("QRSection", parent=styles["Heading2"], spaceBefore=16, spaceAfter=8)
    cell_style = ParagraphStyle("QRCell", parent=styles["Normal"], fontSize=8, leading=10)
    note_style = ParagraphStyle(
        "QRNote", parent=styles["Normal"], fontSize=8.5,
        textColor=colors.HexColor("#6b7280"), spaceAfter=8, leading=11,
    )

    story = []
    if _LOGO_PATH.exists():
        img = Image(str(_LOGO_PATH))
        img.drawHeight = 0.4 * inch
        img.drawWidth = 0.4 * inch * (img.imageWidth / img.imageHeight)
        story.append(img)
        story.append(Spacer(1, 8))

    story.append(Paragraph("Translation Quality Report", title_style))
    scope_bits = ", ".join(f"{k}={v}" for k, v in report.scope.items()) or "all units"
    story.append(Paragraph(
        f"{scope_bits} &nbsp;·&nbsp; evaluator: {report.scoring_provider}"
        f"{(' / ' + report.scoring_model) if report.scoring_model else ''}"
        f" &nbsp;·&nbsp; quality threshold {report.quality_threshold:.0f}"
        f"{(' · style threshold ' + format(report.style_threshold, '.0f')) if report.style_threshold is not None else ''}",
        subtitle_style,
    ))
    story.append(Paragraph(
        f"Generated {(report.finished_at or datetime.utcnow()).strftime('%Y-%m-%d %H:%M UTC')}"
        f"{(' · ' + report.triggered_by) if report.triggered_by else ''}",
        subtitle_style,
    ))
    story.append(Spacer(1, 14))

    # ── Summary ──────────────────────────────────────────────────────────
    t = report.totals
    summary_rows = [
        ["Units evaluated", str(t.get("units", len(items)))],
        ["Below quality threshold (incl. critical)", str(t.get("below_threshold", 0))],
        ["Critical errors (hard fail)", str(t.get("hard_fail", 0))],
        ["Needs review (unscoreable)", str(t.get("needs_review", 0))],
        ["Below style threshold", str(t.get("below_style", 0))],
        ["Estimated source chars to redrive", str(t.get("est_source_chars", 0))],
        ["Commercial-safe / non-commercial / unknown",
         f"{t.get('commercial_safe', 0)} / {t.get('non_commercial', 0)} / {t.get('commercial_unknown', 0)}"],
    ]
    summary = Table(summary_rows, colWidths=[3.6 * inch, 3.4 * inch])
    summary.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#374151")),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.HexColor("#e5e7eb")),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(summary)
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "Recommended actions below are defaults from the quality bucket; a reviewer re-routes "
        "per bucket or per unit before the redrive runs.",
        note_style,
    ))

    # ── Issues table (everything that isn't a clean Pass, worst-first) ────
    issues = sorted(
        [it for it in items if it.bucket.value != "pass"],
        key=lambda it: (it.before_score if it.before_score is not None else -1),
    )
    story.append(Paragraph(f"Quality issues ({len(issues)})", section_style))
    if not issues:
        story.append(Paragraph("Every unit in scope passed. Nothing to redrive.", note_style))
    else:
        header = ["Score", "Bucket", "Action", "Reason", "Commercial"]
        data = [header]
        style_cmds = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")),
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
            ("FONT", (0, 1), (-1, -1), "Helvetica", 8),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e5e7eb")),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        for i, it in enumerate(issues, start=1):
            reason = _clip("; ".join(it.reasons) or ("critical error" if it.hard_fail else "—"))
            comm = {True: "safe", False: "NON-COMM", None: "unknown"}[it.commercial_safe]
            data.append([
                _fmt_score(it.before_score),
                _BUCKET_LABEL.get(it.bucket.value, it.bucket.value),
                _ACTION_LABEL.get(it.recommended_action.value, it.recommended_action.value),
                Paragraph(reason, cell_style),
                comm,
            ])
            style_cmds.append(("TEXTCOLOR", (1, i), (1, i), _BUCKET_COLOR.get(it.bucket.value, colors.black)))
            if it.commercial_safe is False:
                style_cmds.append(("TEXTCOLOR", (4, i), (4, i), colors.HexColor("#e5484d")))
        tbl = Table(data, colWidths=[0.6 * inch, 1.0 * inch, 1.2 * inch, 3.4 * inch, 0.8 * inch], repeatRows=1)
        tbl.setStyle(TableStyle(style_cmds))
        story.append(tbl)

    doc.build(story, onFirstPage=_stamp, onLaterPages=_stamp)
    return buf.getvalue()
