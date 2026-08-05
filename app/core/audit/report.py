"""
Phase 12 — branded PDF report generator for a completed site audit. Turns
the same findings the "Audit" tab renders into a client-facing deliverable:
logo, executive summary, findings grouped by check with severity coloring,
and a closing note — the format the plain-text /export endpoint's report
can't be (a consulting engagement wants something to hand a client, not a
.txt dump).
"""

import io
from datetime import datetime
from pathlib import Path
from typing import List

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from app.models.schemas import SiteAudit, SiteAuditFinding, SiteAuditPage

_LOGO_PATH = Path(__file__).parent.parent.parent / "static" / "branding" / "logo.png"

_SEVERITY_COLOR = {
    "critical": colors.HexColor("#e5484d"),
    "warning": colors.HexColor("#f5a524"),
    "info": colors.HexColor("#3b82f6"),
}

_CHECK_LABEL = {
    "mixed_locale": "Mixed Locale",
    "rtl_readiness": "RTL / Logical CSS Readiness",
    "icu_i18n": "ICU / I18n Tooling",
    "privacy": "Privacy & Regulatory Compliance",
    "text_expansion": "Text Expansion Risk",
    "font_coverage": "Font / Script Coverage",
    "hreflang": "hreflang / SEO Localization",
    "cookie_consent": "Cookie Consent",
    "placeholder_leak": "Untranslated Placeholder Leakage",
    "locale_format": "Locale Format Assumptions",
    "translation_coverage": "Translation Coverage",
    "locale_switcher": "Locale Switcher Integrity",
    "seo_metadata": "SEO Metadata Parity",
    "payment_localization": "Payment Localization",
}

_DETAIL_URL_KEYS = ("url", "from_url", "to_url", "privacy_url", "embed_url")


def _finding_url(finding: SiteAuditFinding) -> str:
    for key in _DETAIL_URL_KEYS:
        value = finding.detail.get(key)
        if value:
            return str(value)
    return ""


def generate_pdf_report(
    audit: SiteAudit, pages: List[SiteAuditPage], findings: List[SiteAuditFinding],
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        topMargin=0.75 * inch, bottomMargin=0.75 * inch, leftMargin=0.75 * inch, rightMargin=0.75 * inch,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("AuditTitle", parent=styles["Title"], fontSize=20, spaceAfter=4)
    subtitle_style = ParagraphStyle("AuditSubtitle", parent=styles["Normal"], fontSize=11, textColor=colors.HexColor("#6b7280"))
    section_style = ParagraphStyle("AuditSection", parent=styles["Heading2"], spaceBefore=18, spaceAfter=8)
    finding_style = ParagraphStyle("AuditFinding", parent=styles["Normal"], fontSize=10, spaceAfter=2, leading=14)
    detail_style = ParagraphStyle("AuditDetail", parent=styles["Normal"], fontSize=8.5, textColor=colors.HexColor("#6b7280"), spaceAfter=8, leading=11)

    story = []

    if _LOGO_PATH.exists():
        story.append(Image(str(_LOGO_PATH), width=0.9 * inch, height=0.9 * inch))
        story.append(Spacer(1, 8))

    story.append(Paragraph("Word in Bits", title_style))
    story.append(Paragraph("Site I18n &amp; Compliance Audit Report", subtitle_style))
    story.append(Spacer(1, 12))

    meta_rows = [
        ["Site audited", audit.root_url],
        ["Primary language", audit.primary_language],
        ["Pages crawled", str(audit.pages_crawled)],
        ["Report generated", datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")],
    ]
    if audit.requester_email:
        meta_rows.insert(1, ["Requested by", audit.requester_email])
    meta_table = Table(meta_rows, colWidths=[1.6 * inch, 4.9 * inch])
    meta_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#6b7280")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 16))

    # ── Executive summary ────────────────────────────────────────────────
    story.append(Paragraph("Executive Summary", section_style))
    by_severity = {"critical": 0, "warning": 0, "info": 0}
    for f in findings:
        by_severity[f.severity.value] = by_severity.get(f.severity.value, 0) + 1

    if findings:
        summary_rows = [["Severity", "Count"]]
        for sev in ("critical", "warning", "info"):
            summary_rows.append([sev.capitalize(), str(by_severity.get(sev, 0))])
        summary_rows.append(["Total findings", str(len(findings))])
        summary_table = Table(summary_rows, colWidths=[2.5 * inch, 1.5 * inch])
        summary_table.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#e5e7eb")),
            ("LINEABOVE", (0, -1), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
            ("TEXTCOLOR", (0, 1), (0, 1), _SEVERITY_COLOR["critical"]),
            ("TEXTCOLOR", (0, 2), (0, 2), _SEVERITY_COLOR["warning"]),
            ("TEXTCOLOR", (0, 3), (0, 3), _SEVERITY_COLOR["info"]),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(summary_table)
    else:
        story.append(Paragraph("No issues found across the pages crawled.", finding_style))

    story.append(PageBreak())

    # ── Findings by check ────────────────────────────────────────────────
    by_check = {}
    for f in findings:
        by_check.setdefault(f.check.value, []).append(f)

    for check, items in by_check.items():
        story.append(Paragraph(f"{_CHECK_LABEL.get(check, check)} ({len(items)})", section_style))
        for f in items:
            color = _SEVERITY_COLOR.get(f.severity.value, colors.black)
            severity_html = f'<font color="{color.hexval()}"><b>{f.severity.value.upper()}</b></font>'
            story.append(Paragraph(f"{severity_html} — {f.summary}", finding_style))
            url = _finding_url(f)
            if url:
                story.append(Paragraph(url, detail_style))
            else:
                story.append(Spacer(1, 6))

    # ── Closing / CTA ────────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph("About This Report", section_style))
    story.append(Paragraph(
        "This automated audit is a starting point for an international-expansion "
        "readiness review, not a substitute for legal advice. Regulatory summaries "
        "reference publicly available jurisdiction data and should be verified with "
        "qualified counsel before launch in a new market.",
        finding_style,
    ))
    story.append(Spacer(1, 12))
    story.append(Paragraph(
        "Prepared by Word in Bits — international content &amp; localization consulting. "
        "Contact us at thewordinbits.com to discuss remediation.",
        finding_style,
    ))

    doc.build(story)
    return buf.getvalue()
