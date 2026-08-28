"""Phase 7 — structured extraction for document formats whose layout matters.
Each extractor turns a binary file into ordered text blocks + a geometry
descriptor per block (ExtractedShape), so the deck/page review can
reconstruct the layout and draw the same rect-based score overlay the inline
review already uses.

  pptx_extract.py  slide decks     (python-pptx, lazy — lxml)
  pdf_extract.py   PDF pages       (pymupdf — no lxml, always available)
  docx_extract.py  flow documents  (python-docx, lazy — lxml); no geometry,
                                    reviewed as a bilingual reader
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ExtractedShape:
    """One text block, with geometry as fractions of the page (0-1) so the
    frontend can render at any size. x/y/w/h are None for blocks with no
    meaningful position (speaker notes, flow-document paragraphs)."""
    page_index: int
    page_width: float
    page_height: float
    shape_index: int
    reading_order: int
    kind: str            # DocumentShapeKind value
    text: str
    x: Optional[float] = None
    y: Optional[float] = None
    w: Optional[float] = None
    h: Optional[float] = None
    is_speaker_note: bool = field(default=False)
