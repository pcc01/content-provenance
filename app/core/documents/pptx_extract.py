"""PPTX text + geometry extraction for the layout-aware deck review (Phase 7),
and the shared slide walk that reinsert.py replays for round-trip export.

python-pptx is lazy-imported (it pulls in lxml, a compiled extension that
some locked-down environments block) — `pptx_available()` returns False on
any import failure and the import endpoint degrades to a clear 503 rather
than the app failing to start. Same pattern as comet_kiwi.py / xcomet.py.

Geometry is emitted as fractions of the slide (0-1) so the frontend can
render at any size without knowing EMU.
"""

import io
from typing import Callable, List, Optional

from app.core.documents import ExtractedShape

__all__ = ["ExtractedShape", "extract_pptx", "pptx_available", "iter_slide_slots"]


def pptx_available() -> bool:
    try:
        import pptx  # noqa: F401
    except Exception:  # ImportError, or an OS/DLL-policy block on lxml
        return False
    return True


def _frac(value, total) -> Optional[float]:
    try:
        if value is None or not total:
            return None
        return round(float(value) / float(total), 5)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _placeholder_kind(shape) -> str:
    try:
        if not getattr(shape, "is_placeholder", False):
            return "other"
        from pptx.enum.shapes import PP_PLACEHOLDER

        ptype = shape.placeholder_format.type
        if ptype in (PP_PLACEHOLDER.TITLE, PP_PLACEHOLDER.CENTER_TITLE, PP_PLACEHOLDER.VERTICAL_TITLE):
            return "title"
        if ptype in (PP_PLACEHOLDER.BODY, PP_PLACEHOLDER.SUBTITLE, PP_PLACEHOLDER.VERTICAL_BODY):
            return "body"
    except Exception:
        pass
    return "other"


def _set_text_frame(tf, value: str) -> None:
    """Replace a text frame's text, keeping the first run's formatting where
    possible (python-pptx's `tf.text =` collapses to one run — acceptable;
    the review already flags a shape whose text outgrew its box)."""
    tf.text = value


class _Slot:
    """One positioned text location on a slide — a text frame or a table
    cell. `.text` reads it, `.set()` replaces it. iter_slide_slots yields
    these in the SAME order extract_pptx emits shapes, so reinsert.py can
    zip translated text back in by position."""

    def __init__(self, kind: str, getter: Callable[[], str], setter: Callable[[str], None]):
        self.kind = kind
        self._get = getter
        self._set = setter

    @property
    def text(self) -> str:
        return (self._get() or "").strip()

    def set(self, value: str) -> None:
        self._set(value)


def iter_slide_slots(slide) -> List[_Slot]:
    """Positioned text slots for a slide, in (top, left) reading order."""
    raw = []
    for shape in slide.shapes:
        top = getattr(shape, "top", None)
        left = getattr(shape, "left", None)
        key = (top if top is not None else 1 << 40, left if left is not None else 1 << 40)

        if getattr(shape, "has_table", False):
            for row in shape.table.rows:
                for cell in row.cells:
                    if (cell.text or "").strip():
                        raw.append((key, _Slot(
                            "table_cell",
                            (lambda c: (lambda: c.text))(cell),
                            (lambda c: (lambda v: setattr(c, "text", v)))(cell),
                        )))
        elif getattr(shape, "has_text_frame", False) and (shape.text_frame.text or "").strip():
            raw.append((key, _Slot(
                _placeholder_kind(shape),
                (lambda tf: (lambda: tf.text))(shape.text_frame),
                (lambda tf: (lambda v: _set_text_frame(tf, v)))(shape.text_frame),
            )))
    raw.sort(key=lambda t: t[0])
    return [slot for _key, slot in raw]


def _notes_paragraphs(slide) -> List[str]:
    if not getattr(slide, "has_notes_slide", False):
        return []
    notes = (slide.notes_slide.notes_text_frame.text or "").strip()
    return [p.strip() for p in notes.split("\n") if p.strip()]


def extract_pptx(raw: bytes) -> List[ExtractedShape]:
    """One ExtractedShape per positioned text slot + speaker-note paragraph,
    in reading order per slide. Raises RuntimeError if python-pptx can't be
    imported — callers gate on pptx_available()."""
    if not pptx_available():
        raise RuntimeError("python-pptx is not importable in this environment.")

    from pptx import Presentation

    prs = Presentation(io.BytesIO(raw))
    sw, sh = float(prs.slide_width or 0), float(prs.slide_height or 0)
    out: List[ExtractedShape] = []

    for page_index, slide in enumerate(prs.slides):
        order = 0
        for kind, text, box in _positioned_with_geometry(slide, sw, sh):
            out.append(ExtractedShape(
                page_index=page_index, page_width=sw, page_height=sh,
                shape_index=order, reading_order=order, kind=kind, text=text,
                x=box[0], y=box[1], w=box[2], h=box[3],
            ))
            order += 1

        for i, para in enumerate(_notes_paragraphs(slide)):
            out.append(ExtractedShape(
                page_index=page_index, page_width=sw, page_height=sh,
                shape_index=10_000 + i, reading_order=order + i,
                kind="speaker_note", text=para, is_speaker_note=True,
            ))

    return out


def _positioned_with_geometry(slide, sw, sh):
    """(kind, text, (x,y,w,h)) per positioned text slot, reading order —
    the geometry-carrying counterpart of iter_slide_slots."""
    raw = []
    for shape in slide.shapes:
        top = getattr(shape, "top", None)
        left = getattr(shape, "left", None)
        key = (top if top is not None else 1 << 40, left if left is not None else 1 << 40)
        box = (_frac(left, sw), _frac(top, sh),
               _frac(getattr(shape, "width", None), sw), _frac(getattr(shape, "height", None), sh))

        if getattr(shape, "has_table", False):
            for row in shape.table.rows:
                for cell in row.cells:
                    if (cell.text or "").strip():
                        raw.append((key, "table_cell", cell.text.strip(), box))
        elif getattr(shape, "has_text_frame", False) and (shape.text_frame.text or "").strip():
            raw.append((key, _placeholder_kind(shape), shape.text_frame.text.strip(), box))
    raw.sort(key=lambda t: t[0])
    return [(kind, text, box) for _k, kind, text, box in raw]
