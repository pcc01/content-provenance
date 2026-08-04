"""
Review Notes API — the notes thread in the review UI's segment drawer.

GET  /api/v1/translations/{unit_id}/notes              - list notes for a unit
POST /api/v1/translations/{unit_id}/notes               - add a note
PUT  /api/v1/translations/{unit_id}/notes/{note_id}/resolve - mark a note resolved/unresolved
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.database import get_db
from app.models.schemas import ReviewNote

router = APIRouter()


class NoteCreateRequest(BaseModel):
    author: str
    body: str
    parent_id: str | None = None


@router.get("/{unit_id}/notes")
async def list_notes(unit_id: str):
    db = get_db()
    notes = await db.list_review_notes(unit_id)
    return [n.model_dump() for n in notes]


@router.post("/{unit_id}/notes", response_model=ReviewNote, status_code=201)
async def create_note(unit_id: str, request: NoteCreateRequest):
    db = get_db()
    unit = await db.get_translation_unit(unit_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Translation unit {unit_id} not found")

    note = ReviewNote(unit_id=unit_id, author=request.author, body=request.body, parent_id=request.parent_id)
    await db.save_review_note(note)
    return note


@router.put("/{unit_id}/notes/{note_id}/resolve", response_model=ReviewNote)
async def resolve_note(unit_id: str, note_id: str, resolved: bool = True):
    db = get_db()
    note = await db.resolve_review_note(note_id, resolved=resolved)
    if not note:
        raise HTTPException(status_code=404, detail=f"Note {note_id} not found")
    return note
