"""In-image OCR (Phase 7) — pull translatable text out of a raster image
(chart labels, screenshots, diagram callouts) so it becomes reviewable
TranslationUnits linked from ImageTranslationUnit.overlay_text_unit_ids.

Uses pytesseract, which needs the Tesseract binary on PATH (or TESSERACT_CMD).
`ocr_available()` checks both the Python package and the binary, and the
endpoint degrades to 503 when either is missing — swap in easyocr/paddleocr
here without changing the API if a torch-based engine is preferred.
"""

import io
from typing import Any, Dict, List

from app.core.config import settings


def ocr_available() -> bool:
    try:
        import pytesseract
    except Exception:
        return False
    try:
        if settings.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def extract_image_text(image_bytes: bytes, lang: str = "eng") -> List[Dict[str, Any]]:
    """One entry per detected text line: {text, x, y, w, h} with the bbox as
    fractions of the image. Raises RuntimeError if OCR isn't available —
    callers gate on ocr_available()."""
    if not ocr_available():
        raise RuntimeError("Tesseract OCR is not available in this environment.")

    import pytesseract
    from PIL import Image

    if settings.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd

    img = Image.open(io.BytesIO(image_bytes))
    iw, ih = img.size
    data = pytesseract.image_to_data(img, lang=lang, output_type=pytesseract.Output.DICT)

    lines: Dict[tuple, Dict[str, Any]] = {}
    for i, word in enumerate(data["text"]):
        if not word.strip():
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        entry = lines.setdefault(key, {"words": [], "x0": x, "y0": y, "x1": x + w, "y1": y + h})
        entry["words"].append(word)
        entry["x0"] = min(entry["x0"], x)
        entry["y0"] = min(entry["y0"], y)
        entry["x1"] = max(entry["x1"], x + w)
        entry["y1"] = max(entry["y1"], y + h)

    out: List[Dict[str, Any]] = []
    for entry in lines.values():
        text = " ".join(entry["words"]).strip()
        if not text:
            continue
        out.append({
            "text": text,
            "x": round(entry["x0"] / iw, 5) if iw else None,
            "y": round(entry["y0"] / ih, 5) if ih else None,
            "w": round((entry["x1"] - entry["x0"]) / iw, 5) if iw else None,
            "h": round((entry["y1"] - entry["y0"]) / ih, 5) if ih else None,
        })
    return out
