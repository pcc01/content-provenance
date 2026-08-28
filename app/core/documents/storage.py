"""Keeps the original bytes of an imported binary document (pptx / pdf / docx)
on the local filesystem, keyed by document id — the source for round-trip
export (reinsert.py). Mirrors the IMAGE_STORAGE_DIR pattern in app/api/images.py.
"""

from pathlib import Path
from typing import Optional

from app.core.config import settings

_EXT = {"pptx": ".pptx", "pdf": ".pdf", "docx": ".docx"}


def _dir() -> Path:
    d = Path(settings.document_storage_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_original(document_id: str, fmt: str, raw: bytes) -> str:
    path = _dir() / f"{document_id}{_EXT.get(fmt, '.bin')}"
    path.write_bytes(raw)
    return str(path)


def load_original(document_id: str, fmt: str) -> Optional[bytes]:
    path = _dir() / f"{document_id}{_EXT.get(fmt, '.bin')}"
    return path.read_bytes() if path.exists() else None
