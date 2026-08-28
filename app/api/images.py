"""
Image Assets API — context screenshots (shown alongside a text segment for
reviewer context) and translatable image assets (their own provenance chain,
e.g. a localized banner).

POST /api/v1/images                              - upload an image asset
GET  /api/v1/images/{id}                          - metadata
GET  /api/v1/images/{id}/file                     - raw file bytes
POST /api/v1/images/{id}/context-link             - attach as context to a translation unit
GET  /api/v1/images/context-links/{unit_id}       - context images linked to a unit
POST /api/v1/images/{id}/localize                 - start (or immediately complete) localizing a source image
PUT  /api/v1/images/localize/{itu_id}/target       - attach/replace the localized target image
GET  /api/v1/images/localize/{itu_id}             - an ImageTranslationUnit's status + provenance
"""

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.core.config import settings
from app.core.database import get_db
from app.core.documents.ocr import extract_image_text, ocr_available
from app.core.prov_builder import build_image_provenance_record, build_provenance_record
from app.core.translation_backends import get_translation_backend
from app.models.schemas import (
    ImageAsset, ImageAssetKind, ImageContextLink, ImageTranslationUnit,
    TranslationMethod, TranslationStatus, TranslationUnit,
)

router = APIRouter()


def _storage_root() -> Path:
    root = Path(settings.image_storage_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


async def _store_file(file: UploadFile, asset_id: str) -> tuple[str, str, str]:
    """Returns (storage_path relative to the storage root, checksum, content_type)."""
    content = await file.read()
    checksum = hashlib.sha256(content).hexdigest()
    ext = Path(file.filename or "").suffix or ""
    relative_path = f"{asset_id}{ext}"
    (_storage_root() / relative_path).write_bytes(content)
    return relative_path, checksum, file.content_type or "application/octet-stream"


@router.post("/", response_model=ImageAsset, status_code=201)
async def upload_image(
    file: UploadFile = File(...),
    kind: ImageAssetKind = Form(ImageAssetKind.CONTEXT),
    alt_text: Optional[str] = Form(None),
    uploaded_by: Optional[str] = Form(None),
):
    db = get_db()
    asset = ImageAsset(
        kind=kind, storage_path="", content_type="", checksum="",
        original_filename=file.filename, alt_text=alt_text, uploaded_by=uploaded_by,
    )
    storage_path, checksum, content_type = await _store_file(file, asset.id)
    asset.storage_path = storage_path
    asset.checksum = checksum
    asset.content_type = content_type
    await db.save_image_asset(asset)
    return asset


@router.get("/{image_id}", response_model=ImageAsset)
async def get_image(image_id: str):
    db = get_db()
    asset = await db.get_image_asset(image_id)
    if not asset:
        raise HTTPException(status_code=404, detail=f"Image {image_id} not found")
    return asset


@router.get("/{image_id}/file", response_class=Response)
async def get_image_file(image_id: str):
    db = get_db()
    asset = await db.get_image_asset(image_id)
    if not asset:
        raise HTTPException(status_code=404, detail=f"Image {image_id} not found")
    path = _storage_root() / asset.storage_path
    if not path.exists():
        raise HTTPException(status_code=404, detail="Image file missing from storage")
    return Response(content=path.read_bytes(), media_type=asset.content_type)


@router.post("/{image_id}/context-link", response_model=ImageContextLink, status_code=201)
async def link_image_as_context(image_id: str, translation_unit_id: str = Form(...), note: Optional[str] = Form(None)):
    db = get_db()
    asset = await db.get_image_asset(image_id)
    if not asset:
        raise HTTPException(status_code=404, detail=f"Image {image_id} not found")
    unit = await db.get_translation_unit(translation_unit_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Translation unit {translation_unit_id} not found")

    link = ImageContextLink(image_id=image_id, translation_unit_id=translation_unit_id, note=note)
    await db.save_image_context_link(link)
    return link


@router.get("/context-links/{translation_unit_id}")
async def get_context_images(translation_unit_id: str):
    db = get_db()
    images = await db.list_context_images_for_unit(translation_unit_id)
    return [i.model_dump() for i in images]


@router.post("/{image_id}/ocr", response_model=ImageTranslationUnit)
async def ocr_image_text(
    image_id: str,
    source_language: str = Form(...),
    target_language: str = Form(...),
    method: TranslationMethod = Form(TranslationMethod.AI),
    itu_id: Optional[str] = Form(None),
    ocr_lang: str = Form("eng"),
):
    """Phase 7 — pull text out of a raster image (chart labels, screenshots,
    diagram callouts): one TranslationUnit per detected line, translated
    immediately, wired into an ImageTranslationUnit's overlay_text_unit_ids
    so the review overlay can box each label on the image. `503` when
    Tesseract isn't available (see app/core/documents/ocr.py)."""
    if not ocr_available():
        raise HTTPException(
            status_code=503,
            detail="Tesseract OCR isn't available — install tesseract and pytesseract, or set TESSERACT_CMD.",
        )
    db = get_db()
    asset = await db.get_image_asset(image_id)
    if not asset:
        raise HTTPException(status_code=404, detail=f"Image {image_id} not found")

    path = _storage_root() / asset.storage_path
    if not path.exists():
        raise HTTPException(status_code=404, detail="Image file not on disk.")
    try:
        lines = extract_image_text(path.read_bytes(), lang=ocr_lang)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OCR failed: {e}")
    if not lines:
        raise HTTPException(status_code=422, detail="No text detected in the image.")

    if method == TranslationMethod.HUMAN:
        agent = await db.get_or_create_agent(
            name="Human Translator", agent_type="Person", metadata={"role": "human_translator"},
        )
    else:
        agent = await db.get_or_create_agent(
            name="claude-3-7-sonnet", agent_type="SoftwareAgent", organization="Anthropic",
        )
    backend = get_translation_backend() if method in (TranslationMethod.AI, TranslationMethod.HYBRID) else None
    now = datetime.utcnow()

    unit_ids: list[str] = []
    for i, line in enumerate(lines):
        if backend:
            translated, confidence = await backend.translate(line["text"], source_language, target_language)
            status = TranslationStatus.COMPLETED
        else:
            translated, confidence = f"[Awaiting human translation] {line['text']}", 1.0
            status = TranslationStatus.PENDING
        unit = TranslationUnit(
            source_id=f"img:{image_id}:{i}", source_text=line["text"], source_language=source_language,
            target_text=translated, target_language=target_language,
            translation_method=method, translated_by_agent_id=agent.id, translated_at=now,
            confidence_score=confidence, status=status,
            metadata={"source_image_id": image_id, "ocr": True, "bbox": {k: line[k] for k in ("x", "y", "w", "h")}},
        )
        await db.save_translation_unit(unit)
        await db.save_provenance_record(await build_provenance_record(unit, []))
        unit_ids.append(unit.id)

    if itu_id:
        itu = await db.get_image_translation_unit(itu_id)
        if not itu:
            raise HTTPException(status_code=404, detail=f"ImageTranslationUnit {itu_id} not found")
        itu.overlay_text_unit_ids = list(dict.fromkeys([*itu.overlay_text_unit_ids, *unit_ids]))
    else:
        itu = ImageTranslationUnit(
            source_image_id=image_id, source_language=source_language, target_language=target_language,
            translation_method=method, translated_by_agent_id=agent.id,
            status=TranslationStatus.PENDING, overlay_text_unit_ids=unit_ids,
        )
    await db.save_image_translation_unit(itu)
    return itu


@router.post("/{image_id}/localize", response_model=ImageTranslationUnit, status_code=201)
async def localize_image(
    image_id: str,
    source_language: str = Form(...),
    target_language: str = Form(...),
    method: TranslationMethod = Form(TranslationMethod.HUMAN),
    translator_name: Optional[str] = Form(None),
    target_file: Optional[UploadFile] = File(None),
):
    """Starts localizing a source image. If target_file is supplied, the
    ImageTranslationUnit is created already-complete; otherwise it's created
    PENDING, awaiting a later PUT .../target upload (e.g. a human designer
    delivering the localized banner separately)."""
    db = get_db()
    source_asset = await db.get_image_asset(image_id)
    if not source_asset:
        raise HTTPException(status_code=404, detail=f"Image {image_id} not found")

    if method == TranslationMethod.HUMAN:
        agent = await db.get_or_create_agent(
            name=translator_name or "Human Translator", agent_type="Person",
            metadata={"role": "human_translator"},
        )
    else:
        agent = await db.get_or_create_agent(
            name=translator_name or "claude-3-7-sonnet", agent_type="SoftwareAgent",
            organization="Anthropic",
        )

    itu = ImageTranslationUnit(
        source_image_id=image_id, source_language=source_language, target_language=target_language,
        translation_method=method, translated_by_agent_id=agent.id, translated_at=datetime.utcnow(),
        status=TranslationStatus.PENDING,
    )

    target_asset: Optional[ImageAsset] = None
    if target_file is not None:
        target_asset = ImageAsset(
            kind=ImageAssetKind.TRANSLATABLE, storage_path="", content_type="", checksum="",
            original_filename=target_file.filename,
        )
        storage_path, checksum, content_type = await _store_file(target_file, target_asset.id)
        target_asset.storage_path = storage_path
        target_asset.checksum = checksum
        target_asset.content_type = content_type
        await db.save_image_asset(target_asset)
        itu.target_image_id = target_asset.id
        itu.status = TranslationStatus.COMPLETED

    await db.save_image_translation_unit(itu)

    prov_record = await build_image_provenance_record(itu, source_asset, target_asset)
    itu.prov_entity_id = prov_record.entities[-1].id
    await db.save_image_translation_unit(itu)
    await db.save_provenance_record(prov_record)

    return itu


@router.put("/localize/{itu_id}/target", response_model=ImageTranslationUnit)
async def attach_localized_image(itu_id: str, target_file: UploadFile = File(...)):
    db = get_db()
    itu = await db.get_image_translation_unit(itu_id)
    if not itu:
        raise HTTPException(status_code=404, detail=f"Image translation unit {itu_id} not found")
    source_asset = await db.get_image_asset(itu.source_image_id)

    target_asset = ImageAsset(
        kind=ImageAssetKind.TRANSLATABLE, storage_path="", content_type="", checksum="",
        original_filename=target_file.filename,
    )
    storage_path, checksum, content_type = await _store_file(target_file, target_asset.id)
    target_asset.storage_path = storage_path
    target_asset.checksum = checksum
    target_asset.content_type = content_type
    await db.save_image_asset(target_asset)

    itu.target_image_id = target_asset.id
    itu.status = TranslationStatus.COMPLETED
    await db.save_image_translation_unit(itu)

    prov_record = await build_image_provenance_record(itu, source_asset, target_asset)
    await db.save_provenance_record(prov_record)

    return itu


@router.get("/localize/{itu_id}")
async def get_image_translation_unit(itu_id: str):
    db = get_db()
    itu = await db.get_image_translation_unit(itu_id)
    if not itu:
        raise HTTPException(status_code=404, detail=f"Image translation unit {itu_id} not found")
    return itu.model_dump()
