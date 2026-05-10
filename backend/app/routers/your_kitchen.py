"""Your Kitchen API — household canon, queue, peculiarities, reactions.

PRD §4.13. All routes are family-scoped via the JWT subject's `family_id`.

    GET    /your-kitchen
    GET    /your-kitchen/dish/{slug_or_id}
    POST   /your-kitchen/queue
    DELETE /your-kitchen/queue/{queue_id}
    POST   /your-kitchen/notes
    DELETE /your-kitchen/notes/{note_id}
    POST   /your-kitchen/react
"""

from __future__ import annotations

import uuid
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.dish import Dish
from app.models.family import Child
from app.services import meal_queue, your_kitchen
from app.services.auth import get_current_child
from app.services.dish_catalog import get_dish_by_id, get_dish_by_slug

router = APIRouter(prefix="/your-kitchen", tags=["your-kitchen"])


# ─── Schemas ─────────────────────────────────────────────────────────────────


class MemberReactionOut(BaseModel):
    person_id: str
    name: str
    sentiment: str
    confidence: float


class DishHouseholdFactsOut(BaseModel):
    dish_id: str
    slug: str
    name: str
    image_url: str | None = None
    cuisine: str
    is_veg: bool
    base_time_minutes: int
    inspired_by_chef: str = ""
    inspired_by_url: str = ""

    times_made: int = 0
    last_served_at: str | None = None
    days_since_last_served: int | None = None
    last_rating: int | None = None

    reactions: list[MemberReactionOut] = []
    love_count: int = 0
    like_count: int = 0
    dislike_count: int = 0
    untried_count: int = 0

    in_cook_repertoire: bool = False
    cook_learned_recently: bool = False

    pinned_note: str | None = None
    note_count: int = 0
    family_pref_summary: str | None = None

    is_queued: bool = False
    queued_by_name: str | None = None
    queued_at: str | None = None


class CanonSectionOut(BaseModel):
    id: str
    title: str
    subtitle: str | None = None
    dishes: list[DishHouseholdFactsOut]


class CanonResponseOut(BaseModel):
    sections: list[CanonSectionOut]
    has_canon: bool
    total_dishes: int


class QueueAddIn(BaseModel):
    dish_id: uuid.UUID | None = None
    slug: str | None = None
    meal_type: str | None = Field(None, max_length=20)
    note: str | None = Field(None, max_length=200)


class QueueEntryOut(BaseModel):
    id: str
    dish_id: str
    slug: str
    name: str
    queued_by_person_id: str | None = None
    meal_type: str | None = None
    note: str | None = None
    status: str
    expires_at: str
    created_at: str


class NoteUpsertIn(BaseModel):
    dish_id: uuid.UUID | None = None
    slug: str | None = None
    body: str = Field(..., min_length=1, max_length=200)
    pinned: bool = False
    # If True, the note is authored by the household (no specific member).
    household_only: bool = False


class NoteOut(BaseModel):
    id: str
    dish_id: str
    body: str
    pinned: bool
    author_person_id: str | None = None
    created_at: str
    updated_at: str


class ReactIn(BaseModel):
    dish_id: uuid.UUID | None = None
    slug: str | None = None
    sentiment: str = Field(..., pattern="^(love|like|dislike|untried)$")
    person_id: uuid.UUID  # explicit so household members can react on behalf of others (kids etc.)


# ─── Helpers ─────────────────────────────────────────────────────────────────


async def _resolve_dish(
    dish_id: uuid.UUID | None,
    slug: str | None,
    db: AsyncSession,
) -> Dish:
    if dish_id is None and not slug:
        raise HTTPException(status_code=400, detail="dish_id or slug is required")
    if dish_id is not None:
        dish = await get_dish_by_id(db, dish_id)
    else:
        dish = await get_dish_by_slug(db, slug)
    if dish is None:
        raise HTTPException(status_code=404, detail="Dish not found")
    return dish


def _facts_to_out(f: your_kitchen.DishHouseholdFacts) -> DishHouseholdFactsOut:
    payload = asdict(f)
    payload["reactions"] = [MemberReactionOut(**r) for r in payload["reactions"]]
    return DishHouseholdFactsOut(**payload)


# ─── Routes ─────────────────────────────────────────────────────────────────


@router.get("", response_model=CanonResponseOut)
async def get_canon(
    db: AsyncSession = Depends(get_db),
    child: Child = Depends(get_current_child),
):
    canon = await your_kitchen.get_canon(child.family_id, db)
    return CanonResponseOut(
        sections=[
            CanonSectionOut(
                id=s.id,
                title=s.title,
                subtitle=s.subtitle,
                dishes=[_facts_to_out(f) for f in s.dishes],
            )
            for s in canon.sections
        ],
        has_canon=canon.has_canon,
        total_dishes=canon.total_dishes,
    )


@router.get("/dish/{slug_or_id}", response_model=DishHouseholdFactsOut)
async def get_dish_facts(
    slug_or_id: str,
    db: AsyncSession = Depends(get_db),
    child: Child = Depends(get_current_child),
):
    try:
        dish_id = uuid.UUID(slug_or_id)
        dish = await get_dish_by_id(db, dish_id)
    except ValueError:
        dish = await get_dish_by_slug(db, slug_or_id)
    if dish is None:
        raise HTTPException(status_code=404, detail="Dish not found")
    facts = await your_kitchen.get_facts_for_dish(child.family_id, dish.id, db)
    if facts is None:
        # Dish exists in the global catalog but the household has never
        # touched it. Synthesize a "fresh" facts record so the dish detail
        # screen still works without 404'ing.
        facts = your_kitchen.DishHouseholdFacts(
            dish_id=str(dish.id),
            slug=dish.slug,
            name=dish.name,
            image_url=dish.image_url,
            cuisine=dish.cuisine,
            is_veg=bool(dish.is_veg),
            base_time_minutes=int(dish.base_time_minutes or 0),
            inspired_by_chef=dish.inspired_by_chef or "",
            inspired_by_url=dish.inspired_by_url or "",
        )
    return _facts_to_out(facts)


@router.post("/queue", response_model=QueueEntryOut, status_code=status.HTTP_201_CREATED)
async def queue_add(
    body: QueueAddIn,
    db: AsyncSession = Depends(get_db),
    child: Child = Depends(get_current_child),
):
    dish = await _resolve_dish(body.dish_id, body.slug, db)
    # Auth: the queueing user is the authenticated child. If a household has
    # multiple Parent entries who *eat* food (PRD §4.13 calls these "active
    # members"), and the child wants to queue on behalf of a member, future
    # iterations can accept an optional `as_person_id` here. For now we use
    # the child's own UUID as the queueing identity so the credit line
    # ("Saved by you") is unambiguous.
    person_id = child.id
    # Snapshot the dish display fields BEFORE invoking the queue write. The
    # write may roll back the session on race-loss (two concurrent inserts
    # of the same (family, dish, person) tuple); after rollback, accessing
    # `dish.slug` triggers a lazy refresh that fails on async sessions
    # (MissingGreenlet). Capturing scalars up front sidesteps the issue
    # entirely and keeps the response 1:1 with the request.
    dish_id_str = str(dish.id)
    dish_slug = dish.slug
    dish_name = dish.name
    entry = await meal_queue.add(
        family_id=child.family_id,
        dish_id=dish.id,
        db=db,
        queued_by_person_id=person_id,
        meal_type=body.meal_type,
        note=body.note,
    )
    await db.commit()
    return QueueEntryOut(
        id=str(entry.id),
        dish_id=dish_id_str,
        slug=dish_slug,
        name=dish_name,
        queued_by_person_id=str(entry.queued_by_person_id) if entry.queued_by_person_id else None,
        meal_type=entry.meal_type,
        note=entry.note,
        status=entry.status,
        expires_at=entry.expires_at.isoformat(),
        created_at=entry.created_at.isoformat(),
    )


@router.delete("/queue/{queue_id}", status_code=status.HTTP_204_NO_CONTENT)
async def queue_remove(
    queue_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    child: Child = Depends(get_current_child),
):
    entry = await meal_queue.get_by_id(queue_id, db)
    if entry is None:
        raise HTTPException(status_code=404, detail="Queue entry not found")
    if entry.family_id != child.family_id:
        raise HTTPException(status_code=403, detail="Not your household's queue entry")
    await meal_queue.remove(queue_id, db)
    await db.commit()
    return None


@router.get("/queue", response_model=list[QueueEntryOut])
async def queue_list(
    db: AsyncSession = Depends(get_db),
    child: Child = Depends(get_current_child),
):
    entries = await meal_queue.list_active(child.family_id, db)
    if not entries:
        return []
    dish_ids = {e.dish_id for e in entries}
    from sqlalchemy import select
    rows = await db.execute(select(Dish).where(Dish.id.in_(dish_ids)))
    by_id = {d.id: d for d in rows.scalars().all()}
    out = []
    for e in entries:
        d = by_id.get(e.dish_id)
        if d is None:
            continue
        out.append(QueueEntryOut(
            id=str(e.id),
            dish_id=str(e.dish_id),
            slug=d.slug,
            name=d.name,
            queued_by_person_id=str(e.queued_by_person_id) if e.queued_by_person_id else None,
            meal_type=e.meal_type,
            note=e.note,
            status=e.status,
            expires_at=e.expires_at.isoformat(),
            created_at=e.created_at.isoformat(),
        ))
    return out


@router.post("/notes", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
async def notes_upsert(
    body: NoteUpsertIn,
    db: AsyncSession = Depends(get_db),
    child: Child = Depends(get_current_child),
):
    dish = await _resolve_dish(body.dish_id, body.slug, db)
    author_id: uuid.UUID | None = None if body.household_only else child.id
    note = await your_kitchen.upsert_note(
        family_id=child.family_id,
        dish_id=dish.id,
        body=body.body,
        db=db,
        author_person_id=author_id,
        pinned=body.pinned,
    )
    await db.commit()
    return NoteOut(
        id=str(note.id),
        dish_id=str(note.dish_id),
        body=note.body,
        pinned=note.pinned,
        author_person_id=str(note.author_person_id) if note.author_person_id else None,
        created_at=note.created_at.isoformat(),
        updated_at=note.updated_at.isoformat(),
    )


@router.get("/notes/{slug_or_id}", response_model=list[NoteOut])
async def notes_list(
    slug_or_id: str,
    db: AsyncSession = Depends(get_db),
    child: Child = Depends(get_current_child),
):
    try:
        dish_id = uuid.UUID(slug_or_id)
        dish = await get_dish_by_id(db, dish_id)
    except ValueError:
        dish = await get_dish_by_slug(db, slug_or_id)
    if dish is None:
        raise HTTPException(status_code=404, detail="Dish not found")
    notes = await your_kitchen.list_notes(child.family_id, dish.id, db)
    return [
        NoteOut(
            id=str(n.id),
            dish_id=str(n.dish_id),
            body=n.body,
            pinned=n.pinned,
            author_person_id=str(n.author_person_id) if n.author_person_id else None,
            created_at=n.created_at.isoformat(),
            updated_at=n.updated_at.isoformat(),
        )
        for n in notes
    ]


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def notes_delete(
    note_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    child: Child = Depends(get_current_child),
):
    from app.models.your_kitchen import DishHouseholdNote
    note = await db.get(DishHouseholdNote, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    if note.family_id != child.family_id:
        raise HTTPException(status_code=403, detail="Not your household's note")
    await your_kitchen.delete_note(note_id, db)
    await db.commit()
    return None


@router.post("/react", status_code=status.HTTP_204_NO_CONTENT)
async def react(
    body: ReactIn,
    db: AsyncSession = Depends(get_db),
    child: Child = Depends(get_current_child),
):
    dish = await _resolve_dish(body.dish_id, body.slug, db)
    await your_kitchen.react(
        family_id=child.family_id,
        dish_id=dish.id,
        person_id=body.person_id,
        sentiment=body.sentiment,
        db=db,
    )
    await db.commit()
    return None
