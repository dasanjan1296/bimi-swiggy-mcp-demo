"""Saved Recipes API — household-curated YouTube / Instagram recipe
links. Drives the home "Self cook ideas" sheet's "Your recipes"
section and the Settings management screen.

Endpoints:
  POST   /saved-recipes              create (with optional oEmbed hydration)
  GET    /saved-recipes              list active recipes by family
  PATCH  /saved-recipes/{id}         partial edit
  DELETE /saved-recipes/{id}         soft-delete (sets is_active=False)

Dedup: re-saving a URL the household already has returns the existing
row with 200 instead of inserting a duplicate.
"""
from __future__ import annotations

import logging
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.saved_recipe import SavedRecipe
from app.services.youtube_oembed import (
    detect_platform,
    fetch_youtube_metadata,
)


logger = logging.getLogger("bimi")
router = APIRouter(prefix="/saved-recipes", tags=["saved-recipes"])


# ── Schemas ──────────────────────────────────────────────────────────


CourseLiteral = Literal["breakfast", "lunch", "dinner", "snack", "any"]
PlatformLiteral = Literal["youtube", "instagram", "web"]


class SavedRecipeOut(BaseModel):
    id: str
    family_id: str
    created_by_name: str | None = None
    source_url: str
    source_platform: PlatformLiteral
    title: str
    description: str | None = None
    image_url: str | None = None
    notes: str | None = None
    course: CourseLiteral
    total_time_mins: int | None = None
    tags: list[str] | None = None
    is_active: bool

    model_config = {"from_attributes": True}


class SavedRecipeCreate(BaseModel):
    family_id: uuid.UUID
    source_url: HttpUrl
    created_by_name: str | None = Field(default=None, max_length=120)
    # All other fields are optional. For YouTube, the server's oEmbed
    # call hydrates whatever the user didn't provide (title / image).
    # For Instagram and generic web, the user must provide at least a
    # title — IG's metadata endpoint requires Meta Graph approval and
    # we don't want to ship that scope today.
    title: str | None = Field(default=None, max_length=255)
    description: str | None = None
    image_url: str | None = None
    notes: str | None = None
    course: CourseLiteral = "any"
    total_time_mins: int | None = Field(default=None, ge=0, le=720)
    tags: list[str] | None = None


class SavedRecipePatch(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    description: str | None = None
    image_url: str | None = None
    notes: str | None = None
    course: CourseLiteral | None = None
    total_time_mins: int | None = Field(default=None, ge=0, le=720)
    tags: list[str] | None = None


# ── Helpers ──────────────────────────────────────────────────────────


def _to_out(r: SavedRecipe) -> SavedRecipeOut:
    return SavedRecipeOut(
        id=str(r.id),
        family_id=str(r.family_id),
        created_by_name=r.created_by_name,
        source_url=r.source_url,
        source_platform=r.source_platform,  # type: ignore[arg-type]
        title=r.title,
        description=r.description,
        image_url=r.image_url,
        notes=r.notes,
        course=r.course,  # type: ignore[arg-type]
        total_time_mins=r.total_time_mins,
        tags=r.tags,
        is_active=r.is_active,
    )


# ── Endpoints ────────────────────────────────────────────────────────


@router.post("", response_model=SavedRecipeOut, status_code=201)
async def create_saved_recipe(
    body: SavedRecipeCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create (or return existing) a household-saved recipe.

    Server-side platform detection. For YouTube URLs, we additionally
    fire oEmbed to fill in `title` / `image_url` if the client didn't
    pass them — saves the user from typing what we can already get for
    free. Instagram and other web URLs must come with a `title`.

    De-duplication: if (family_id, source_url) already exists active,
    we return that existing row with 200 (and let the FE toast
    "Already saved"). Soft-deleted duplicates are revived (set back to
    is_active=True) rather than re-inserted.
    """
    source_url = str(body.source_url)
    platform = detect_platform(source_url)

    # ── Dedup ──
    existing_q = await db.execute(
        select(SavedRecipe).where(
            SavedRecipe.family_id == body.family_id,
            SavedRecipe.source_url == source_url,
        )
    )
    existing = existing_q.scalar_one_or_none()
    if existing is not None:
        # Revive a soft-deleted match so the user gets back what they
        # remember saving instead of seeing a "didn't exist" surface.
        if not existing.is_active:
            existing.is_active = True
        await db.commit()
        await db.refresh(existing)
        return _to_out(existing)

    # ── Hydrate from oEmbed when YouTube ──
    title = (body.title or "").strip() or None
    image_url = body.image_url or None
    description = body.description or None

    if platform == "youtube":
        metadata = await fetch_youtube_metadata(source_url)
        if metadata is not None:
            if not title:
                title = metadata.title
            if not image_url:
                image_url = metadata.thumbnail_url
            # Description = author byline so the card shows where it
            # came from. User-supplied description always wins.
            if not description and metadata.author_name:
                description = f"From {metadata.author_name}"

    if not title:
        # IG / web URL with no title — user must provide one.
        raise HTTPException(
            status_code=422,
            detail="Title is required for non-YouTube URLs.",
        )

    row = SavedRecipe(
        family_id=body.family_id,
        created_by_name=body.created_by_name,
        source_url=source_url,
        source_platform=platform,
        title=title,
        description=description,
        image_url=image_url,
        notes=body.notes,
        course=body.course,
        total_time_mins=body.total_time_mins,
        tags=body.tags,
        is_active=True,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _to_out(row)


@router.get("", response_model=list[SavedRecipeOut])
async def list_saved_recipes(
    family_id: uuid.UUID = Query(...),
    course: CourseLiteral | None = Query(
        None,
        description=(
            "Filter by course. `any` matches recipes saved without a "
            "specific course; pass a meal type (e.g. `lunch`) to get "
            "matching recipes plus the `any`-tagged ones."
        ),
    ),
    db: AsyncSession = Depends(get_db),
):
    """List a household's active saved recipes.

    When a specific `course` is requested, we also include recipes
    with `course="any"` (the user's "show this for any meal" bucket).
    Sorted newest-first so the user sees what they just added at the
    top of the SelfCookSheet.
    """
    query = (
        select(SavedRecipe)
        .where(SavedRecipe.family_id == family_id)
        .where(SavedRecipe.is_active.is_(True))
    )
    if course and course != "any":
        # Surface this course's recipes AND the "any"-bucket so the
        # user's "general" saves still show up when they're looking
        # for a specific meal type.
        query = query.where(SavedRecipe.course.in_([course, "any"]))
    elif course == "any":
        query = query.where(SavedRecipe.course == "any")

    query = query.order_by(SavedRecipe.created_at.desc())
    result = await db.execute(query)
    return [_to_out(r) for r in result.scalars().all()]


@router.patch("/{recipe_id}", response_model=SavedRecipeOut)
async def patch_saved_recipe(
    recipe_id: uuid.UUID,
    body: SavedRecipePatch,
    db: AsyncSession = Depends(get_db),
):
    """Partial update. Only the fields present in the request body are
    written; everything else is left alone. No-op patches still bump
    `updated_at` (the model's onupdate hook).
    """
    result = await db.execute(
        select(SavedRecipe).where(SavedRecipe.id == recipe_id)
    )
    row = result.scalar_one_or_none()
    if row is None or not row.is_active:
        raise HTTPException(status_code=404, detail="Saved recipe not found")

    updates = body.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(row, key, value)
    await db.commit()
    await db.refresh(row)
    return _to_out(row)


@router.delete("/{recipe_id}", status_code=204)
async def delete_saved_recipe(
    recipe_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete: sets `is_active=False`. The row sticks around so
    re-saving the same URL revives it (see POST dedup logic) instead
    of creating a new one.
    """
    result = await db.execute(
        select(SavedRecipe).where(SavedRecipe.id == recipe_id)
    )
    row = result.scalar_one_or_none()
    if row is None or not row.is_active:
        # 204 either way — idempotent delete.
        return None
    row.is_active = False
    await db.commit()
    return None
