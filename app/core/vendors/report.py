"""Phase 14 — branded PDF vendor scorecard, the same reportlab pattern as
app/core/audit/report.py's site-audit report: logo, summary table, ranked
rows. Turns the scorecard API's JSON into something to actually hand a
vendor in a renegotiation, not a raw number.
"""

import io
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.models.schemas import VendorScorecardEntry

_LOGO_PATH = Path(__file__).parent.parent.parent / "static" / "branding" / "logo.png"


def _fmt_score(score: Optional[float]) -> str:
    return f"{score:.1f}" if score is not None else "—"


def _score_color(score: Optional[float]):
    if score is None:
        return colors.HexColor("#6b7280")
    if score >= 85:
        return colors.HexColor("#2f9e44")
    if score >= 70:
        return colors.HexColor("#f5a524")
    return colors.HexColor("#e5484d")


def generate_vendor_scorecard_pdf(
    entries: List[VendorScorecardEntry], target_language: Optional[str] = None,
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        topMargin=0.75 * inch, bottomMargin=0.75 * inch, leftMargin=0.75 * inch, rightMargin=0.75 * inch,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("VendorTitle", parent=styles["Title"], fontSize=20, spaceAfter=4)
    subtitle_style = ParagraphStyle(
        "VendorSubtitle", parent=styles["Normal"], fontSize=11, textColor=colors.HexColor("#6b7280"),
    )
    section_style = ParagraphStyle("VendorSection", parent=styles["Heading2"], spaceBefore=18, spaceAfter=8)
    note_style = ParagraphStyle(
        "VendorNote", parent=styles["Normal"], fontSize=8.5,
        textColor=colors.HexColor("#6b7280"), spaceAfter=8, leading=11,
    )

    story = []
    if _LOGO_PATH.exists():
        story.append(Image(str(_LOGO_PATH), width=0.9 * inch, height=0.9 * inch))
        story.append(Spacer(1, 8))

    story.append(Paragraph("Word in Bits", title_style))
    story.append(Paragraph("Localization Vendor &amp; Agent Scorecard", subtitle_style))
    story.append(Spacer(1, 12))

    meta_rows = [
        ["Scope", target_language or "All target languages"],
        ["Report generated", datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")],
    ]
    meta_table = Table(meta_rows, colWidths=[1.6 * inch, 4.9 * inch])
    meta_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#6b7280")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 16))

    story.append(Paragraph("Ranking", section_style))
    if not entries:
        story.append(Paragraph("No scored translations found for this scope.", note_style))
    else:
        header = ["Vendor / Agent", "Units", "Quality", "Style", "Tone", "Voice", "Terminology"]
        rows = [header]
        for e in entries:
            rows.append([
                e.organization, str(e.unit_count), _fmt_score(e.avg_quality_score),
                _fmt_score(e.avg_style_score), _fmt_score(e.avg_tone_score),
                _fmt_score(e.avg_voice_score), _fmt_score(e.avg_terminology_score),
            ])
        table = Table(rows, colWidths=[1.7 * inch] + [0.75 * inch] * 6)
        style_cmds = [
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#e5e7eb")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
        ]
        for row_idx, e in enumerate(entries, start=1):
            style_cmds.append(("TEXTCOLOR", (2, row_idx), (2, row_idx), _score_color(e.avg_quality_score)))
            style_cmds.append(("TEXTCOLOR", (3, row_idx), (3, row_idx), _score_color(e.avg_style_score)))
        table.setStyle(TableStyle(style_cmds))
        story.append(table)

    story.append(Spacer(1, 16))
    story.append(Paragraph(
        "Quality is translation accuracy (MQM-style critical/major/minor error scoring). "
        "Style is overall tone/voice/terminology adherence against configured style guides — "
        "both 0-100, higher is better. — marks a category with no scored data yet.",
        note_style,
    ))

    doc.build(story)
    return buf.getvalue()
