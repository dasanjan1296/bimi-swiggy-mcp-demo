"""Dish-notes API — household-shared free-text instructions for a
dish, captured when rating a past meal in the home rate-meals sheet.

Endpoints:
  POST   /dish-notes                  create a note
  GET    /dish-notes?family_id=&...   list notes (filter by date / dish)
  PATCH  /dish-notes/{id}             edit own note
  DELETE /dish-notes/{id}             soft-delete

Author identity is a free-text byline (no real auth in this app yet).
The PATCH / DELETE endpoints accept an `author_name` query / body
field as a soft check — same pattern as `saved_recipes`.
"""
from __future__ import annotations

import logging
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.dish_note import DishNote
from app.services.dish_notes import (
    list_notes_for_date,
    list_notes_for_dish,
)


logger = logging.getLogger("bimi")
router = APIRouter(prefix="/dish-notes", tags=["dish-notes"])


# ── Schemas ──────────────────────────────────────────────────────────


MealTypeLiteral = Literal["breakfast", "lunch", "dinner", "snack"]


class DishNoteOut(BaseModel):
    id: str
    family_id: str
    author_name: str
    dish_name: str
    meal_type: MealTypeLiteral | None = None
    source_date: str
    note_text: str
    is_active: bool

    model_config = {"from_attributes": True}


class DishNoteCreate(BaseModel):
    family_id: uuid.UUID
    author_name: str = Field(..., min_length=1, max_length=120)
    dish_name: str = Field(..., min_length=1, max_length=255)
    meal_type: MealTypeLiteral | None = None
    source_date: str = Field(..., min_length=10, max_length=10)
    note_text: str = Field(..., min_length=1, max_length=600)


class DishNotePatch(BaseModel):
    note_text: str | None = Field(default=None, min_length=1, max_length=600)


# ── Helpers ──────────────────────────────────────────────────────────


def _to_out(n: DishNote) -> DishNoteOut:
    return DishNoteOut(
        id=str(n.id),
        family_id=str(n.family_id),
        author_name=n.author_name,
        dish_name=n.dish_name,
        meal_type=n.meal_type,  # type: ignore[arg-type]
        source_date=n.source_date,
        note_text=n.note_text,
        is_active=n.is_active,
    )


# ── Endpoints ────────────────────────────────────────────────────────


@router.post("", response_model=DishNoteOut, status_code=201)
async def create_dish_note(
    body: DishNoteCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new dish note. The household sees every note in the
    past-day modal regardless of author; only the author can later
    edit / delete via PATCH / DELETE.
    """
    row = DishNote(
        family_id=body.family_id,
        author_name=body.author_name.strip(),
        dish_name=body.dish_name.strip(),
        meal_type=body.meal_type,
        source_date=body.source_date,
        note_text=body.note_text.strip(),
        is_active=True,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    # Analytics — captures cook-instruction signal for the InstaCook
    # profile (notes encode "we want X done differently next time"
    # which is preference data the recommender can use).
    try:
        from app.routers.meals import _resolve_dish_taxonomy
        from app.services.analytics import track

        cuisine, is_veg = await _resolve_dish_taxonomy(body.dish_name, db)
        await track(
            "note.created",
            family_id=body.family_id,
            actor_type="child",
            properties={
                "dish": body.dish_name,
                "cuisine": cuisine,
                "is_veg": is_veg,
                "meal_type": body.meal_type,
                "source_date": body.source_date,
                "note_length": len(body.note_text),
            },
            db=db,
        )
    except Exception:  # noqa: BLE001
        logger.exception("analytics.track(note.created) failed")

    return _to_out(row)


@router.get("", response_model=list[DishNoteOut])
async def list_dish_notes(
    family_id: uuid.UUID = Query(...),
    dish_name: str | None = Query(
        None,
        description=(
            "Filter to a single dish (case-insensitive). When supplied "
            "without `date`, returns the latest notes for the dish "
            "across all past occurrences."
        ),
    ),
    date: str | None = Query(
        None,
        description=(
            "Filter to a single yyyy-mm-dd source date. When supplied, "
            "returns every note authored against that day's meals."
        ),
        min_length=10,
        max_length=10,
    ),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List notes for a household. Filters compose:

    - `dish_name` only       -> cook-brief lookup (latest per dish)
    - `date` only            -> past-day modal lookup
    - both supplied          -> "notes for THIS dish on THIS day"
    - neither supplied       -> all active household notes (caller
                                cap via `limit`; mostly a debug path)
    """
    if date:
        rows = await list_notes_for_date(family_id, date, db)
        if dish_name:
            wanted = dish_name.strip().lower()
            rows = [r for r in rows if r.dish_name.lower() == wanted]
        return [_to_out(r) for r in rows[:limit]]

    if dish_name:
        rows = await list_notes_for_dish(family_id, dish_name, db, limit=limit)
        return [_to_out(r) for r in rows]

    # Generic listing — used rarely (admin / debug). Newest first.
    result = await db.execute(
        select(DishNote)
        .where(DishNote.family_id == family_id)
        .where(DishNote.is_active.is_(True))
        .order_by(DishNote.created_at.desc())
        .limit(limit)
    )
    return [_to_out(r) for r in result.scalars().all()]


@router.patch("/{note_id}", response_model=DishNoteOut)
async def patch_dish_note(
    note_id: uuid.UUID,
    body: DishNotePatch,
    author_name: str = Query(
        ...,
        description=(
            "Free-text author byline; must match the original author "
            "to be allowed to edit. Soft check pending real auth."
        ),
        min_length=1,
        max_length=120,
    ),
    db: AsyncSession = Depends(get_db),
):
    """Partial update — currently only `note_text` is editable.
    Author byline is matched as a string (no real auth in this app
    yet). Returns 404 for missing rows + 403 for cross-author edits.
    """
    result = await db.execute(
        select(DishNote).where(DishNote.id == note_id)
    )
    row = result.scalar_one_or_none()
    if row is None or not row.is_active:
        raise HTTPException(status_code=404, detail="Note not found")
    if row.author_name.strip().lower() != author_name.strip().lower():
        raise HTTPException(
            status_code=403,
            detail="Only the original author can edit this note.",
        )

    if body.note_text is not None:
        row.note_text = body.note_text.strip()

    await db.commit()
    await db.refresh(row)
    return _to_out(row)


@router.delete("/{note_id}", status_code=204)
async def delete_dish_note(
    note_id: uuid.UUID,
    author_name: str = Query(
        ...,
        description="Author byline; must match the original author.",
        min_length=1,
        max_length=120,
    ),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete (sets is_active=False). Idempotent — already-deleted
    rows return 204 silently so the FE doesn't have to check first.
    """
    result = await db.execute(
        select(DishNote).where(DishNote.id == note_id)
    )
    row = result.scalar_one_or_none()
    if row is None or not row.is_active:
        return None
    if row.author_name.strip().lower() != author_name.strip().lower():
        raise HTTPException(
            status_code=403,
            detail="Only the original author can delete this note.",
        )
    row.is_active = False
    await db.commit()
    return None
