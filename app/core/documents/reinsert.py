"""Round-trip export (Phase 7) — write translated text back into the original
.pptx / .docx, preserving layout. Both paths lazy-import their parser
(python-pptx / python-docx, lxml) and raise RuntimeError when it isn't
available; the API endpoint turns that into a 503.

The mapping is positional: reinsert replays the exact same slide / paragraph
walk the extractor used, so the k-th text location gets the k-th translation.
Character-run formatting inside a shape is flattened to one run (python-pptx /
python-docx behaviour) — the review already flags a shape whose translation
outgrew its box.
"""

import io
from typing import Dict, List

__all__ = ["reinsert_pptx", "reinsert_docx"]


def reinsert_pptx(
    raw: bytes, positioned_by_slide: Dict[int, List[str]], notes_by_slide: Dict[int, List[str]],
) -> bytes:
    from pptx import Presentation

    from app.core.documents.pptx_extract import iter_slide_slots

    prs = Presentation(io.BytesIO(raw))
    for page_index, slide in enumerate(prs.slides):
        targets = positioned_by_slide.get(page_index, [])
        for i, slot in enumerate(iter_slide_slots(slide)):
            if i < len(targets) and targets[i] is not None:
                slot.set(targets[i])

        notes = notes_by_slide.get(page_index, [])
        if notes:
            slide.notes_slide.notes_text_frame.text = "\n".join(notes)

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def reinsert_docx(raw: bytes, ordered_targets: List[str]) -> bytes:
    import docx

    document = docx.Document(io.BytesIO(raw))
    it = iter(ordered_targets)

    def _next():
        return next(it, None)

    for para in document.paragraphs:
        if (para.text or "").strip():
            v = _next()
            if v is not None:
                para.text = v

    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                if (cell.text or "").strip():
                    v = _next()
                    if v is not None:
                        cell.text = v

    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()
