"""Dish-note service helpers — single place for the cook-brief
composer and the past-day modal endpoint to read DishNote rows.

Two consumer queries dominate the load:

  • Cook morning brief: "the latest N notes for dish X across all
    household members." `list_notes_for_dish` covers it. Returns
    notes newest-first so the most recent feedback wins when the
    cook has limited attention to the briefing.

  • Past-day modal: "every note any member has written that ties
    back to a specific meal occurrence (yyyy-mm-dd)." The
    `source_date` column makes this a direct lookup.

`format_for_cook_brief` keeps the briefing-line shape next to the
fetch logic so the composer doesn't need to know the byline format.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dish_note import DishNote


async def list_notes_for_dish(
    family_id: uuid.UUID,
    dish_name: str,
    db: AsyncSession,
    limit: int = 5,
) -> list[DishNote]:
    """Return active notes for `dish_name` in `family_id`, newest first.

    Case-insensitive match on `dish_name` so "Maggi" matches "maggi"
    matches "MAGGI" — the recipe archive doesn't enforce case
    consistency, so neither should our notes lookup.
    """
    if not dish_name.strip():
        return []
    result = await db.execute(
        select(DishNote)
        .where(DishNote.family_id == family_id)
        .where(DishNote.is_active.is_(True))
        # PostgreSQL `lower()` rather than ILIKE — exact equality on
        # the lowered value uses the index when present and is
        # unambiguously a case-insensitive equality.
        .where(DishNote.dish_name.ilike(dish_name))
        .order_by(DishNote.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def list_notes_for_date(
    family_id: uuid.UUID,
    source_date: str,
    db: AsyncSession,
) -> list[DishNote]:
    """Return active notes authored against `source_date` for the
    family. Used by the past-day modal — group by `dish_name` upstream
    if the consumer wants per-meal grouping.
    """
    result = await db.execute(
        select(DishNote)
        .where(DishNote.family_id == family_id)
        .where(DishNote.source_date == source_date)
        .where(DishNote.is_active.is_(True))
        .order_by(DishNote.created_at.asc())
    )
    return list(result.scalars().all())


def format_for_cook_brief(notes: list[DishNote]) -> list[str]:
    """Render notes as bullet lines for the WhatsApp morning brief.

    Each line: `- {Author}: {note}` — kept terse and bylined so the
    cook can mentally route preferences ("Anjan wants less salt" vs
    "Mayank doesn't eat garlic") without re-reading the household
    roster every time. Trailing punctuation isn't normalised; users
    type the way they type.
    """
    return [f"- {n.author_name}: {n.note_text}" for n in notes]
