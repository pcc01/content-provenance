"""PDF text + geometry extraction (Phase 7). Uses PyMuPDF (`pymupdf` / `fitz`),
which is a self-contained compiled wheel — no lxml — so unlike the pptx/docx
extractors this one is always available. One ExtractedShape per text block,
geometry as fractions of the page.
"""

from statistics import median
from typing import List

from app.core.documents import ExtractedShape


def pdf_available() -> bool:
    try:
        import pymupdf  # noqa: F401
    except Exception:
        try:
            import fitz  # noqa: F401
        except Exception:
            return False
    return True


def _open(raw: bytes):
    try:
        import pymupdf as fitz
    except Exception:
        import fitz
    return fitz.open(stream=raw, filetype="pdf")


def extract_pdf(raw: bytes) -> List[ExtractedShape]:
    """One block per contiguous text region PyMuPDF reports, in its reading
    order. The largest-font block near the top of a page is tagged 'title',
    the rest 'body'."""
    if not pdf_available():
        raise RuntimeError("pymupdf is not importable in this environment.")

    doc = _open(raw)
    out: List[ExtractedShape] = []
    try:
        for page_index in range(doc.page_count):
            page = doc.load_page(page_index)
            pw, ph = float(page.rect.width), float(page.rect.height)
            data = page.get_text("dict")
            blocks = [b for b in data.get("blocks", []) if b.get("type", 1) == 0]

            sizes = []
            rendered = []
            for b in blocks:
                text_parts, block_sizes = [], []
                for line in b.get("lines", []):
                    for span in line.get("spans", []):
                        t = span.get("text", "")
                        if t.strip():
                            text_parts.append(t)
                            block_sizes.append(span.get("size", 0) or 0)
                text = " ".join(" ".join(text_parts).split())
                if not text:
                    continue
                bx0, by0, bx1, by1 = b.get("bbox", (0, 0, 0, 0))
                mx = max(block_sizes) if block_sizes else 0
                sizes.append(mx)
                rendered.append((text, mx, (bx0, by0, bx1, by1)))

            body_size = median(sizes) if sizes else 0
            max_size = max(sizes) if sizes else 0
            for order, (text, mx, (bx0, by0, bx1, by1)) in enumerate(rendered):
                near_top = (by0 / ph if ph else 1) < 0.35
                bigger = body_size and (mx >= body_size * 1.2 or (mx == max_size and mx > body_size))
                is_title = bool(bigger and near_top)
                out.append(ExtractedShape(
                    page_index=page_index, page_width=pw, page_height=ph,
                    shape_index=order, reading_order=order,
                    kind="title" if is_title else "body", text=text,
                    x=round(bx0 / pw, 5) if pw else None,
                    y=round(by0 / ph, 5) if ph else None,
                    w=round((bx1 - bx0) / pw, 5) if pw else None,
                    h=round((by1 - by0) / ph, 5) if ph else None,
                ))
    finally:
        doc.close()
    return out
