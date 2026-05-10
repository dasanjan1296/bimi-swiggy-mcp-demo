"""Meal suggestion and logging API."""

import logging
import uuid
from datetime import UTC, date, datetime, timedelta

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.family import Child, Parent
from app.models.meal import MealLog
from app.services.auth import get_current_child, require_family_scoped_access
from app.services.meal_engine import get_recent_meals, log_meal, suggest_meals

router = APIRouter(prefix="/meals", tags=["meals"])


class MealLogOut(BaseModel):
    id: uuid.UUID
    family_id: uuid.UUID
    date: date
    meal_type: str
    dishes: list[str]
    cooked_by: uuid.UUID | None = None
    source: str
    notes: str | None = None
    rating: int | None = None
    feedback: str | None = None

    model_config = {"from_attributes": True}


class MealLogCreate(BaseModel):
    meal_type: str
    dishes: list[str]
    cooked_by: uuid.UUID | None = None
    source: str = "home_cook"
    notes: str | None = None


class MealSelectRequest(BaseModel):
    meal_type: str
    option_index: int
    cook_id: uuid.UUID | None = None


class MealFeedbackRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    feedback: str | None = None


class MealPlanRequest(BaseModel):
    meal_date: date
    meal_type: str = "lunch"
    option_index: int
    fallback_index: int | None = None
    cook_arrival_time: str | None = None  # HH:MM format
    auto_order: bool = False


class MealPlanOut(BaseModel):
    id: uuid.UUID
    family_id: uuid.UUID
    date: date
    meal_type: str
    selected_meal: str
    dishes: list[str]
    fallback_meal: str | None = None
    fallback_dishes: list[str] | None = None
    auto_order: bool
    status: str
    cart_id: uuid.UUID | None = None
    recipe_source_id: uuid.UUID | None = None
    recipe_locked_at: datetime | None = None

    model_config = {"from_attributes": True}


class SwitchRecipeRequest(BaseModel):
    recipe_source_id: uuid.UUID


@router.get("", response_model=list[MealLogOut])
async def list_meals(
    days: int = 7,
    current_child: Child = Depends(get_current_child),
    db: AsyncSession = Depends(get_db),
):
    meals = await get_recent_meals(current_child.family_id, db, days)
    return meals


@router.post("", response_model=MealLogOut)
async def create_meal_log(
    data: MealLogCreate,
    current_child: Child = Depends(get_current_child),
    db: AsyncSession = Depends(get_db),
):
    meal = await log_meal(
        family_id=current_child.family_id,
        meal_type=data.meal_type,
        dishes=data.dishes,
        cooked_by=data.cooked_by,
        source=data.source,
        notes=data.notes,
        db=db,
    )
    await db.commit()
    await db.refresh(meal)
    return meal


@router.get("/suggest")
async def get_meal_suggestions(
    meal_type: str = "lunch",
    current_child: Child = Depends(get_current_child),
    db: AsyncSession = Depends(get_db),
):
    suggestions = await suggest_meals(current_child.family_id, meal_type, db)
    return suggestions


@router.post("/select")
async def select_meal(
    data: MealSelectRequest,
    current_child: Child = Depends(get_current_child),
    db: AsyncSession = Depends(get_db),
):
    """Select a meal option — logs it, notifies the cook, and queues missing ingredients."""
    suggestions = await suggest_meals(current_child.family_id, data.meal_type, db)
    options = suggestions.get("options", [])

    if data.option_index < 0 or data.option_index >= len(options):
        raise HTTPException(status_code=400, detail="Invalid option index")

    selected = options[data.option_index]

    meal = await log_meal(
        family_id=current_child.family_id,
        meal_type=data.meal_type,
        dishes=selected.get("dishes", []),
        cooked_by=data.cook_id,
        source="home_cook",
        notes=f"Selected: {selected.get('name', '')}",
        db=db,
    )

    # Notify the cook via WhatsApp with recipe tutorial link
    if data.cook_id:
        result = await db.execute(
            select(Parent).where(Parent.id == data.cook_id)
        )
        cook = result.scalar_one_or_none()
        if cook:
            from app.services.whatsapp import send_text_message
            dishes_str = ", ".join(selected.get("dishes", []))
            msg = f"✅ Aaj {data.meal_type} mein banaye:\n{dishes_str}\n\nSahab/Ma'am ne approve kar diya hai. 👍"

            youtube_url = selected.get("youtube_url")
            if youtube_url:
                msg += f"\n\n🎬 Recipe video dekho: {youtube_url}"

            await send_text_message(cook.whatsapp_id, msg)

    # Queue missing ingredients into the grocery cart
    missing = selected.get("missing_ingredients", [])
    if missing:
        from app.services.intent import extract_intent
        missing_names = ", ".join(m["name"] for m in missing)
        intent = await extract_intent(
            f"Need for cooking: {missing_names}",
            family_id=current_child.family_id,
            source="meal_engine",
        )
        if intent.items:
            from app.services.confirmation import handle_extraction
            family_children = await db.execute(
                select(Child).where(Child.family_id == current_child.family_id)
            )
            await handle_extraction(
                data.cook_id or current_child.id,
                current_child.family_id,
                cook.whatsapp_id if data.cook_id and cook else "",
                intent,
                db,
            )

    await db.commit()
    return {
        "status": "selected",
        "meal": MealLogOut.model_validate(meal),
        "missing_ingredients_queued": len(missing),
        "youtube_url": selected.get("youtube_url"),
    }


@router.post("/{meal_id}/feedback", response_model=MealLogOut)
async def submit_feedback(
    meal_id: uuid.UUID,
    data: MealFeedbackRequest,
    current_child: Child = Depends(get_current_child),
    db: AsyncSession = Depends(get_db),
):
    """Submit optional rating + text feedback for a logged meal."""
    result = await db.execute(
        select(MealLog).where(
            and_(MealLog.id == meal_id, MealLog.family_id == current_child.family_id)
        )
    )
    meal = result.scalar_one_or_none()
    if not meal:
        raise HTTPException(404, "Meal not found")

    meal.rating = data.rating
    meal.feedback = data.feedback
    meal.feedback_at = datetime.now(UTC)

    # HCG learning from meal feedback (Thompson Sampling posterior update)
    try:
        from app.models.person_context import PersonContext
        from app.services.thompson_meals import record_meal_feedback
        person_result = await db.execute(
            select(PersonContext.parent_id).where(
                PersonContext.family_id == current_child.family_id,
                PersonContext.is_active == True,
                PersonContext.parent_id.isnot(None),
            )
        )
        person_ids = [row[0] for row in person_result.all()]
        for dish in (meal.dishes or []):
            await record_meal_feedback(
                current_child.family_id, person_ids, dish, data.rating, db,
            )
    except Exception:  # noqa: BLE001 — best-effort meal-feedback recording
        logger.exception("record_meal_feedback failed for meal %s", meal.id)

    # HCG life event detection from feedback text
    if data.feedback:
        try:
            from app.services.temporal_engine import detect_life_events, handle_life_event
            events = detect_life_events(data.feedback)
            for event in events:
                for pid in person_ids:
                    await handle_life_event(current_child.family_id, pid, event, db)
        except Exception:  # noqa: BLE001 — best-effort life-event detection
            logger.exception("life-event detection from feedback failed for meal %s", meal.id)

    await db.commit()
    await db.refresh(meal)
    return meal


@router.get("/pending-feedback", response_model=list[MealLogOut])
async def pending_feedback(
    current_child: Child = Depends(get_current_child),
    db: AsyncSession = Depends(get_db),
):
    """Return today's meals that haven't received feedback yet — used for soft nudge UI."""
    from datetime import date as date_type

    result = await db.execute(
        select(MealLog).where(
            and_(
                MealLog.family_id == current_child.family_id,
                MealLog.date == date_type.today(),
                MealLog.rating.is_(None),
            )
        ).order_by(MealLog.meal_type)
    )
    return list(result.scalars().all())


# ── Meal Pre-Planning ───────────────────────────────────────────────────


@router.get("/preplan/suggest")
async def get_preplan_suggestions(
    meal_date: date,
    meal_type: str = "lunch",
    current_child: Child = Depends(get_current_child),
    db: AsyncSession = Depends(get_db),
):
    """Get meal suggestions enriched with pre-planning metadata (ordering needs, fallbacks)."""
    from app.services.meal_preplanning import suggest_preplan
    return await suggest_preplan(current_child.family_id, meal_date, meal_type, db)


@router.post("/preplan", response_model=MealPlanOut)
async def create_preplan(
    data: MealPlanRequest,
    current_child: Child = Depends(get_current_child),
    db: AsyncSession = Depends(get_db),
):
    """
    Plan a meal for a future date. Selects the primary option and an optional
    zero-ordering fallback. Missing ingredients are auto-ordered (or sent for
    approval) before the cook arrives.
    """
    from app.services.meal_preplanning import create_meal_plan, suggest_preplan

    suggestions = await suggest_preplan(
        current_child.family_id, data.meal_date, data.meal_type, db
    )
    options = suggestions.get("options", [])
    fallback_options = suggestions.get("fallback_options", [])

    if data.option_index < 0 or data.option_index >= len(options):
        raise HTTPException(400, "Invalid option index")

    selected = options[data.option_index]
    fallback = None
    if data.fallback_index is not None:
        if 0 <= data.fallback_index < len(fallback_options):
            fallback = fallback_options[data.fallback_index]

    cook_time = None
    if data.cook_arrival_time:
        from datetime import time as time_type
        parts = data.cook_arrival_time.split(":")
        cook_time = time_type(int(parts[0]), int(parts[1]))

    plan = await create_meal_plan(
        family_id=current_child.family_id,
        meal_date=data.meal_date,
        meal_type=data.meal_type,
        selected_option=selected,
        fallback_option=fallback,
        cook_arrival=cook_time,
        auto_order=data.auto_order,
        db=db,
    )
    await db.commit()
    await db.refresh(plan)
    return plan


@router.get("/preplan", response_model=list[MealPlanOut])
async def list_preplans(
    from_date: date | None = None,
    current_child: Child = Depends(get_current_child),
    db: AsyncSession = Depends(get_db),
):
    """List meal plans for the family, optionally from a given date."""
    from app.models.meal_plan import MealPlan

    query = select(MealPlan).where(MealPlan.family_id == current_child.family_id)
    if from_date:
        query = query.where(MealPlan.date >= from_date)
    query = query.order_by(MealPlan.date, MealPlan.meal_type)

    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/preplan/{plan_id}", response_model=MealPlanOut)
async def get_preplan(
    plan_id: uuid.UUID,
    current_child: Child = Depends(get_current_child),
    db: AsyncSession = Depends(get_db),
):
    from app.models.meal_plan import MealPlan

    result = await db.execute(
        select(MealPlan).where(
            and_(MealPlan.id == plan_id, MealPlan.family_id == current_child.family_id)
        )
    )
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(404, "Meal plan not found")
    return plan


@router.patch("/preplan/{plan_id}/recipe", response_model=MealPlanOut)
async def switch_preplan_recipe(
    plan_id: uuid.UUID,
    body: SwitchRecipeRequest,
    current_child: Child = Depends(get_current_child),
    db: AsyncSession = Depends(get_db),
):
    """Swap the pinned recipe link on a meal plan.

    Returns 409 if the cook has already been briefed (the plan's
    `recipe_locked_at` is set). Returns 400 if the recipe doesn't
    belong to this family or doesn't match the plan's headline dish.
    """
    from app.models.meal_plan import MealPlan
    from app.services.recipe_link_service import (
        RecipeLockedError,
        switch_plan_recipe,
    )

    result = await db.execute(
        select(MealPlan).where(
            and_(MealPlan.id == plan_id, MealPlan.family_id == current_child.family_id)
        )
    )
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(404, "Meal plan not found")

    try:
        await switch_plan_recipe(
            plan=plan, new_recipe_source_id=body.recipe_source_id, db=db,
        )
    except RecipeLockedError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    await db.commit()
    await db.refresh(plan)
    return plan


# ── Cross-device meal history + per-member feedback ─────────────────


class FeedbackByKeyRequest(BaseModel):
    """Submit or upsert a per-member rating for a planned meal,
    keyed on the natural tuple (family, date, meal_type, dish, member).

    The legacy `POST /meals/{meal_id}/feedback` endpoint required the
    server's UUID for a `meal_logs` row; the FE only knew the local
    mock id so the call always 404'd. This endpoint accepts what the
    FE actually has."""

    family_id: uuid.UUID
    member_id: str = Field(min_length=1, max_length=255)
    member_name: str = Field(min_length=1, max_length=255)
    meal_date: date
    meal_type: str = Field(min_length=1, max_length=20)
    dish_name: str = Field(min_length=1, max_length=255)
    rating: int = Field(ge=1, le=5)
    feedback: str | None = Field(default=None, max_length=1000)


class FeedbackByKeyOut(BaseModel):
    family_id: uuid.UUID
    meal_date: date
    meal_type: str
    dish_name: str
    rating: int


@router.post("/feedback", response_model=FeedbackByKeyOut)
async def submit_feedback_by_key(
    body: FeedbackByKeyRequest,
    current_child: Child = Depends(get_current_child),
    db: AsyncSession = Depends(get_db),
):
    """Upsert a rating for a meal identified by its natural key.

    Writes/updates a `meal_logs` row scoped to (family, date,
    meal_type). Per-member rating shape will land in a follow-up
    migration; for now we surface the household-level rating because
    `meal_logs` doesn't carry a member_id today.

    Emits a `meal.rated` analytics event with InstaCook-relevant
    dimensions (cuisine, dietary, spice) so the profile pipeline can
    rebuild member preferences from raw events when the model evolves.
    """
    if body.family_id != current_child.family_id:
        raise HTTPException(403, "Family mismatch")

    # Find or create a MealLog for this meal slot. Legacy data may
    # carry multiple rows for the same (family, date, meal_type) tuple
    # because the older `/meals/{meal_id}/feedback` endpoint inserted
    # per-id rows; we deterministically upsert into the most recent
    # one rather than assuming uniqueness.
    existing_q = await db.execute(
        select(MealLog).where(
            MealLog.family_id == body.family_id,
            MealLog.date == body.meal_date,
            MealLog.meal_type == body.meal_type,
        ).order_by(MealLog.created_at.desc()).limit(1)
    )
    log = existing_q.scalar_one_or_none()
    if log is None:
        log = MealLog(
            family_id=body.family_id,
            date=body.meal_date,
            meal_type=body.meal_type,
            dishes=[body.dish_name],
            source="home_cook",
            rating=body.rating,
            feedback=body.feedback,
            feedback_at=datetime.now(UTC),
        )
        db.add(log)
    else:
        # Preserve the dish list; just update the rating + feedback.
        log.rating = body.rating
        if body.feedback:
            log.feedback = body.feedback
        log.feedback_at = datetime.now(UTC)

    await db.commit()

    # Hcg learning hook — keep the existing Thompson posterior update
    # alive so the new endpoint stays compatible with the recommender.
    try:
        from app.models.person_context import PersonContext
        from app.services.thompson_meals import record_meal_feedback
        person_result = await db.execute(
            select(PersonContext.parent_id).where(
                PersonContext.family_id == body.family_id,
                PersonContext.is_active == True,
                PersonContext.parent_id.isnot(None),
            )
        )
        person_ids = [row[0] for row in person_result.all()]
        await record_meal_feedback(
            body.family_id, person_ids, body.dish_name, body.rating, db,
        )
    except Exception:  # noqa: BLE001
        logger.exception("record_meal_feedback failed for family=%s dish=%s",
                         body.family_id, body.dish_name)

    # Resolve dish taxonomy for the InstaCook event payload.
    cuisine, is_veg = await _resolve_dish_taxonomy(body.dish_name, db)

    try:
        from app.services.analytics import track
        await track(
            "meal.rated",
            family_id=body.family_id,
            actor_type="child",
            actor_id=current_child.id,
            properties={
                "member_id": body.member_id,
                "dish": body.dish_name,
                "cuisine": cuisine,
                "is_veg": is_veg,
                "meal_type": body.meal_type,
                "meal_date": body.meal_date.isoformat(),
                "rating": body.rating,
                "has_feedback_text": bool(body.feedback),
            },
            db=db,
        )
    except Exception:  # noqa: BLE001
        logger.exception("analytics.track(meal.rated) failed")

    return FeedbackByKeyOut(
        family_id=body.family_id,
        meal_date=body.meal_date,
        meal_type=body.meal_type,
        dish_name=body.dish_name,
        rating=body.rating,
    )


# ── Helpers ─────────────────────────────────────────────────────────


async def _resolve_dish_taxonomy(
    dish_name: str, db: AsyncSession,
) -> tuple[str | None, bool | None]:
    """Look up cuisine + is_veg for a dish name. Returns (None, None)
    when the dish isn't in the catalogue (custom suggestions). Cheap
    LIKE lookup — there are ~50 curated dishes today."""
    from app.models.dish import Dish

    try:
        result = await db.execute(
            select(Dish.cuisine, Dish.is_veg).where(
                Dish.name.ilike(dish_name.strip())
            ).limit(1)
        )
        row = result.first()
        if row is None:
            return None, None
        return row[0], row[1]
    except Exception:  # noqa: BLE001
        return None, None
