"""Recipe link sharing across household members and the cook.

Slice 1 of the WhatsApp coordination plan: when a household member
shares a YouTube/Instagram recipe link in their 1:1 chat with Bimi,
we save it to the family catalog (`RecipeSource`) and promote it as
the default for that dish. Future meal plans for that dish auto-pin
this link; the cook morning brief carries the pinned link to the cook.

Members can swap the pinned recipe right up until the cook is briefed.
After that the plan's `recipe_locked_at` is set and switches are
rejected — the cook has already been told what to make.

This module deliberately does NOT call any LLM. Cooks are competent
to follow a YouTube video; we just facilitate the link plumbing.
"""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.meal_plan import MealPlan
from app.models.recipe_source import RecipeSource

logger = logging.getLogger("bimi.recipe_link")


class RecipeLockedError(Exception):
    """Raised when a switch is attempted after the cook has been briefed."""


async def save_recipe_link(
    *,
    family_id: uuid.UUID,
    dish_name: str,
    youtube_url: str,
    contributed_by_id: str | None,
    contributed_by_name: str | None,
    contributed_by_role: str = "member",
    channel_name: str | None = None,
    video_title: str | None = None,
    thumbnail_url: str | None = None,
    source_platform: str = "youtube",
    db: AsyncSession,
) -> RecipeSource:
    """Save a shared recipe link and make it the family's new default for the dish.

    Newest wins per the product spec — any existing defaults for the
    same `(family_id, dish_name)` get demoted in the same transaction.

    The dish-name is normalised to a canonical form (Title Case, no
    surrounding whitespace) before lookup so different members typing
    "paneer butter masala" / "Paneer Butter Masala" / " paneer butter
    masala " collapse onto the same catalog entry.
    """
    canonical_dish = _canonical_dish_name(dish_name)

    # Demote prior defaults for this dish — newest wins.
    prior = await db.execute(
        select(RecipeSource).where(
            and_(
                RecipeSource.family_id == family_id,
                RecipeSource.dish_name == canonical_dish,
                RecipeSource.is_default.is_(True),
            )
        )
    )
    for r in prior.scalars().all():
        r.is_default = False

    recipe = RecipeSource(
        family_id=family_id,
        dish_name=canonical_dish,
        youtube_url=youtube_url,
        channel_name=channel_name,
        video_title=video_title,
        source_platform=source_platform,
        thumbnail_url=thumbnail_url,
        contributed_by_id=contributed_by_id,
        contributed_by_name=contributed_by_name,
        contributed_by_role=contributed_by_role,
        is_default=True,
    )
    db.add(recipe)
    await db.flush()

    # Re-pin onto any unlocked future meal plans already containing
    # this dish — so a recipe shared after a plan is created still
    # reaches the cook, as long as the brief hasn't gone out.
    await _repin_unlocked_plans(
        family_id=family_id,
        dish_name=canonical_dish,
        recipe_source_id=recipe.id,
        db=db,
    )

    logger.info(
        "recipe_link_saved family=%s dish=%s url=%s by=%s",
        family_id, canonical_dish, youtube_url, contributed_by_name,
    )
    return recipe


async def get_default_for_dish(
    *,
    family_id: uuid.UUID,
    dish_name: str,
    db: AsyncSession,
) -> RecipeSource | None:
    """Return the family's pinned recipe for a dish, or None if none saved."""
    canonical = _canonical_dish_name(dish_name)
    result = await db.execute(
        select(RecipeSource)
        .where(
            and_(
                RecipeSource.family_id == family_id,
                RecipeSource.dish_name == canonical,
            )
        )
        .order_by(RecipeSource.is_default.desc(), RecipeSource.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def attach_recipe_to_plan(
    *,
    plan: MealPlan,
    db: AsyncSession,
) -> RecipeSource | None:
    """Resolve the default recipe for the plan's headline dish and pin it.

    Behaviour:
      - Locked plan → no-op (returns None).
      - Unlocked plan with a pinned recipe whose dish still matches
        the headline → no-op.
      - Unlocked plan with a pinned recipe whose dish drifted (vote
        re-locked to a different dish) → clear the stale pin and
        re-resolve.
      - Unlocked plan without a pinned recipe → resolve from the
        family default and pin if available.

    Returns the attached `RecipeSource`, or None if nothing was
    available or the plan was locked.

    Multi-dish plans (e.g. "dal + roti + sabzi") track the FIRST dish
    in `plan.dishes` — household members curate links for the headline
    dish, not for staples like roti.
    """
    if plan.recipe_locked_at is not None:
        return None

    dish = _headline_dish(plan)
    if not dish:
        return None

    canonical = _canonical_dish_name(dish)

    # Drop a stale pin whose dish no longer matches the plan headline.
    if plan.recipe_source_id is not None:
        existing = await db.get(RecipeSource, plan.recipe_source_id)
        if existing is not None and existing.dish_name == canonical:
            return existing
        plan.recipe_source_id = None

    recipe = await get_default_for_dish(
        family_id=plan.family_id, dish_name=dish, db=db,
    )
    if not recipe:
        return None

    plan.recipe_source_id = recipe.id
    await db.flush()
    return recipe


async def switch_plan_recipe(
    *,
    plan: MealPlan,
    new_recipe_source_id: uuid.UUID,
    db: AsyncSession,
) -> RecipeSource:
    """Swap the pinned recipe on a plan. Rejects if the plan is locked.

    Raises:
        RecipeLockedError: if `recipe_locked_at` is set (cook briefed).
        ValueError: if the new recipe doesn't belong to the same
            family or doesn't match the plan's headline dish.
    """
    if plan.recipe_locked_at is not None:
        raise RecipeLockedError(
            f"Plan {plan.id} recipe locked at {plan.recipe_locked_at.isoformat()}"
        )

    new_recipe = await db.get(RecipeSource, new_recipe_source_id)
    if new_recipe is None or new_recipe.family_id != plan.family_id:
        raise ValueError("Recipe not found in this family's catalog")

    headline = _headline_dish(plan)
    if headline and _canonical_dish_name(headline) != new_recipe.dish_name:
        raise ValueError(
            f"Recipe '{new_recipe.dish_name}' does not match plan dish '{headline}'"
        )

    plan.recipe_source_id = new_recipe.id
    await db.flush()
    return new_recipe


async def lock_plan_recipe(
    *,
    plan: MealPlan,
    db: AsyncSession,
) -> None:
    """Mark the plan's recipe as locked. Idempotent."""
    if plan.recipe_locked_at is None:
        plan.recipe_locked_at = datetime.now(UTC)
        await db.flush()


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


async def _repin_unlocked_plans(
    *,
    family_id: uuid.UUID,
    dish_name: str,
    recipe_source_id: uuid.UUID,
    db: AsyncSession,
) -> int:
    """When a newer recipe is shared, re-pin it onto unlocked plans
    that already feature the dish. Returns the count re-pinned.
    """
    today = datetime.now(UTC).date()
    plans_q = await db.execute(
        select(MealPlan).where(
            and_(
                MealPlan.family_id == family_id,
                MealPlan.date >= today,
                MealPlan.recipe_locked_at.is_(None),
            )
        )
    )
    repinned = 0
    for plan in plans_q.scalars().all():
        headline = _headline_dish(plan)
        if not headline:
            continue
        if _canonical_dish_name(headline) != dish_name:
            continue
        plan.recipe_source_id = recipe_source_id
        repinned += 1
    if repinned:
        await db.flush()
    return repinned


def _headline_dish(plan: MealPlan) -> str | None:
    """Pick the dish that the recipe link should track."""
    if plan.dishes:
        first = next((d for d in plan.dishes if d), None)
        if first:
            return first
    return plan.selected_meal or None


def _canonical_dish_name(raw: str) -> str:
    """Collapse casing/whitespace differences so 'paneer butter masala'
    and 'Paneer Butter Masala' map onto the same catalog row.
    """
    return " ".join(raw.strip().split()).title()
