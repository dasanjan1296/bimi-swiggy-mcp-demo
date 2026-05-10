import logging
import uuid
from datetime import UTC, date as date_t, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.family import Child
from app.models.meal_plan import MealPlan, MealPlanStatus
from app.models.recipe_source import RecipeSource
from app.models.vote import MealVote
from app.services.auth import require_family_scoped_access

logger = logging.getLogger("bimi")
router = APIRouter(tags=["voting"])


class VoteSubmit(BaseModel):
    # Loop 15: tighten input bounds. A buggy or malicious client could
    # otherwise submit `rating: 999999` which would poison Nash fairness
    # scoring (downstream weights compute `rating / max_rating`).
    member_id: str = Field(min_length=1, max_length=255)
    member_name: str = Field(min_length=1, max_length=255)
    meal_type: str = Field(default="lunch", max_length=20)
    dish_name: str = Field(min_length=1, max_length=255)
    rating: int = Field(ge=1, le=5)
    # Optional — when omitted the server defaults to "tomorrow", which
    # preserves the legacy single-day vote contract. Cross-device sync
    # passes the actual target date so future-week votes route to the
    # right row.
    meal_date: date_t | None = None
    # AI proxy task sets this true; member-submitted votes leave it
    # default false. Surfaces in the past-day modal as "AI voted X" and
    # is used by the InstaCook profile pipeline to discount implicit
    # preference signal from proxy votes.
    is_proxy: bool = False


class VoteOut(BaseModel):
    member_id: str
    member_name: str
    dish_name: str
    rating: int

    class Config:
        from_attributes = True


class SuggestionOut(BaseModel):
    id: str
    dish_name: str
    confidence: float
    fairness_score: float
    novelty_bonus: float
    prep_time: str
    needs_advance_prep: bool
    advance_prep_note: str | None = None
    constraints: list[dict] = []
    ingredients: list[str] = []
    missing_ingredients: list[str] = []
    source_url: str | None = None
    source_platform: str | None = None
    source_thumbnail: str | None = None
    suggested_by_id: str | None = None
    suggested_by_name: str | None = None
    note_for_cook: str | None = None


class DishSuggestionRequest(BaseModel):
    dish_name: str
    source_url: str | None = None
    note_for_cook: str | None = None
    suggested_by_id: str | None = None
    suggested_by_name: str | None = None
    meal_type: str = "lunch"


class FairnessScoreOut(BaseModel):
    member_id: str
    member_name: str
    satisfaction_score: float
    meals_served: int
    avg_satisfaction: float
    is_underserved: bool


class TomorrowResponse(BaseModel):
    date: str
    suggestions: dict[str, list[SuggestionOut]]
    votes: list[VoteOut]
    fairness_scores: list[FairnessScoreOut]


class VotingResults(BaseModel):
    meal_type: str
    date: str
    votes: list[VoteOut]
    dish_rankings: list[dict]
    fairness_scores: list[FairnessScoreOut]


class FinalizeRequest(BaseModel):
    meal_type: str = "lunch"
    dish_name: str
    dishes: list[str]
    # Optional target date (defaults to "tomorrow"). Supplied by the
    # cross-device sync flow when the user finalises a future day from
    # the wheel of meals.
    meal_date: date_t | None = None
    # True only when the AI proxy task closes a vote that no member
    # answered in time. Past-day modal labels this differently and
    # InstaCook profile aggregation weights proxy days lower.
    finalized_by_proxy: bool = False


MOCK_SUGGESTIONS = {
    "breakfast": [
        SuggestionOut(id="s-b1", dish_name="Aloo Paratha with Curd", confidence=0.87, fairness_score=0.92, novelty_bonus=0.1, prep_time="25 min", needs_advance_prep=False),
        SuggestionOut(id="s-b2", dish_name="Poha with Chai", confidence=0.79, fairness_score=0.88, novelty_bonus=0.3, prep_time="15 min", needs_advance_prep=False),
        SuggestionOut(id="s-b3", dish_name="Idli Sambar", confidence=0.71, fairness_score=0.95, novelty_bonus=0.5, prep_time="30 min", needs_advance_prep=True, advance_prep_note="Soak urad dal overnight for batter"),
    ],
    "lunch": [
        SuggestionOut(id="s-l1", dish_name="Chole with Bhature", confidence=0.91, fairness_score=0.85, novelty_bonus=0.2, prep_time="45 min", needs_advance_prep=True, advance_prep_note="Soak chole (chickpeas) overnight"),
        SuggestionOut(id="s-l2", dish_name="Rajma Chawal", confidence=0.84, fairness_score=0.90, novelty_bonus=0.15, prep_time="40 min", needs_advance_prep=True, advance_prep_note="Soak rajma overnight"),
        SuggestionOut(id="s-l3", dish_name="Paneer Butter Masala with Jeera Rice", confidence=0.82, fairness_score=0.78, novelty_bonus=0.05, prep_time="35 min", needs_advance_prep=False,
                      constraints=[{"type": "health", "description": "High fat content — cholesterol concern", "memberName": "Rahul", "severity": "warning"}]),
    ],
    "dinner": [
        SuggestionOut(id="s-d1", dish_name="Dal Tadka with Roti", confidence=0.88, fairness_score=0.94, novelty_bonus=0.1, prep_time="30 min", needs_advance_prep=False),
        SuggestionOut(id="s-d2", dish_name="Aloo Gobi with Paratha", confidence=0.80, fairness_score=0.87, novelty_bonus=0.25, prep_time="35 min", needs_advance_prep=False),
        SuggestionOut(id="s-d3", dish_name="Mix Veg with Pulao", confidence=0.76, fairness_score=0.91, novelty_bonus=0.4, prep_time="40 min", needs_advance_prep=False),
    ],
}

MOCK_FAIRNESS = [
    FairnessScoreOut(member_id="m-001", member_name="Rahul", satisfaction_score=0.72, meals_served=12, avg_satisfaction=3.8, is_underserved=False),
    FairnessScoreOut(member_id="m-002", member_name="Priya", satisfaction_score=0.85, meals_served=14, avg_satisfaction=4.2, is_underserved=False),
    FairnessScoreOut(member_id="m-003", member_name="Arjun", satisfaction_score=0.58, meals_served=9, avg_satisfaction=3.2, is_underserved=True),
    FairnessScoreOut(member_id="m-004", member_name="Ananya", satisfaction_score=0.65, meals_served=11, avg_satisfaction=3.5, is_underserved=True),
]


@router.get("/families/{family_id}/voting/tomorrow", response_model=TomorrowResponse)
async def get_tomorrow_suggestions(
    family_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access),
):
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).date()

    result = await db.execute(
        select(MealVote).where(
            MealVote.family_id == family_id,
            MealVote.meal_date_d == tomorrow,
        )
    )
    votes = result.scalars().all()

    return TomorrowResponse(
        date=tomorrow.isoformat(),
        suggestions=MOCK_SUGGESTIONS,
        votes=[VoteOut(member_id=v.member_id, member_name=v.member_name, dish_name=v.dish_name, rating=v.rating) for v in votes],
        fairness_scores=MOCK_FAIRNESS,
    )


@router.post("/families/{family_id}/voting/vote", response_model=VoteOut)
async def submit_vote(
    family_id: uuid.UUID,
    body: VoteSubmit,
    db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access),
):
    """Idempotent vote submit. Loop 9: race-safe via DB-level UNIQUE +
    IntegrityError fallback (in case two workers pass the pre-check at
    the same time).

    Migration 053 widened this endpoint:
      - accepts a typed `meal_date` so future-week votes route to the
        right row (legacy callers omit it and get "tomorrow")
      - accepts `is_proxy` so the AI proxy task can mark the vote
      - writes both the legacy `meal_date` text column and the new
        `meal_date_d` Date column during the transition
      - emits a `vote.cast` analytics event with InstaCook-relevant
        dimensions (cuisine, is_veg) so profile aggregation can rebuild
        member preferences from raw events
    """
    from sqlalchemy.exc import IntegrityError

    target_date = body.meal_date or (datetime.now(UTC) + timedelta(days=1)).date()
    target_date_str = target_date.isoformat()

    async def _find_existing() -> MealVote | None:
        result = await db.execute(
            select(MealVote).where(
                MealVote.family_id == family_id,
                MealVote.member_id == body.member_id,
                MealVote.meal_date_d == target_date,
                MealVote.meal_type == body.meal_type,
                MealVote.dish_name == body.dish_name,
            )
        )
        return result.scalar_one_or_none()

    vote = await _find_existing()
    is_new = vote is None

    if vote:
        vote.rating = body.rating
        vote.is_proxy = body.is_proxy
        await db.commit()
        await db.refresh(vote)
    else:
        vote = MealVote(
            family_id=family_id,
            member_id=body.member_id,
            member_name=body.member_name,
            meal_date=target_date_str,
            meal_date_d=target_date,
            meal_type=body.meal_type,
            dish_name=body.dish_name,
            rating=body.rating,
            is_proxy=body.is_proxy,
        )
        db.add(vote)
        try:
            await db.commit()
            await db.refresh(vote)
        except IntegrityError:
            # Another worker beat us to the INSERT. Roll back, re-fetch
            # the row that won, and apply our rating as an update — keeps
            # the API idempotent.
            await db.rollback()
            vote = await _find_existing()
            if vote is None:
                raise
            vote.rating = body.rating
            vote.is_proxy = body.is_proxy
            await db.commit()
            await db.refresh(vote)
            is_new = False

    # Analytics — fire after the row is durable. Wrapped in try so a
    # downstream telemetry hiccup never breaks the user-facing flow.
    try:
        from app.routers.meals import _resolve_dish_taxonomy
        from app.services.analytics import track

        cuisine, is_veg = await _resolve_dish_taxonomy(body.dish_name, db)
        await track(
            "vote.cast" if is_new else "vote.updated",
            family_id=family_id,
            actor_type="bimi" if body.is_proxy else "child",
            actor_id=None,
            properties={
                "member_id": body.member_id,
                "dish": body.dish_name,
                "cuisine": cuisine,
                "is_veg": is_veg,
                "meal_type": body.meal_type,
                "meal_date": target_date_str,
                "rating": body.rating,
                "is_proxy": body.is_proxy,
            },
            db=db,
        )
    except Exception:  # noqa: BLE001
        logger.exception("analytics.track(vote.*) failed")

    return VoteOut(
        member_id=vote.member_id,
        member_name=vote.member_name,
        dish_name=vote.dish_name,
        rating=vote.rating,
    )


@router.get("/families/{family_id}/voting/results", response_model=VotingResults)
async def get_voting_results(
    family_id: uuid.UUID,
    meal_type: str = "lunch",
    db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access),
):
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).date()

    result = await db.execute(
        select(MealVote).where(
            MealVote.family_id == family_id,
            MealVote.meal_date_d == tomorrow,
            MealVote.meal_type == meal_type,
        )
    )
    votes = result.scalars().all()

    dish_scores: dict[str, list[int]] = {}
    for v in votes:
        dish_scores.setdefault(v.dish_name, []).append(v.rating)

    rankings = sorted(
        [
            {"dish_name": name, "avg_rating": sum(ratings) / len(ratings), "vote_count": len(ratings)}
            for name, ratings in dish_scores.items()
        ],
        key=lambda x: (-x["avg_rating"], -x["vote_count"]),
    )

    return VotingResults(
        meal_type=meal_type,
        date=tomorrow.isoformat(),
        votes=[VoteOut(member_id=v.member_id, member_name=v.member_name, dish_name=v.dish_name, rating=v.rating) for v in votes],
        dish_rankings=rankings,
        fairness_scores=MOCK_FAIRNESS,
    )


@router.post("/families/{family_id}/voting/finalize")
async def finalize_plan(
    family_id: uuid.UUID,
    body: FinalizeRequest,
    db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access),
):
    """Finalise a meal for the household.

    Idempotent on (family_id, date, meal_type) — a second finalise for
    the same slot updates the existing row instead of inserting a
    duplicate. The cross-device sync flow re-finalises on every device
    that picks the dish, and the wheel keeps an optimistic local
    update before the server round-trip lands.
    """
    target_date = body.meal_date or (datetime.now(UTC) + timedelta(days=1)).date()
    target_date_str = target_date.isoformat()

    # Upsert. We deliberately don't add a unique constraint on
    # (family, date, meal_type) yet because multiple existing
    # backends rely on append-only meal_plans (planning + cooking
    # status state machine). Soft idempotency via SELECT-then-UPDATE
    # is good enough for now.
    existing_q = await db.execute(
        select(MealPlan).where(
            MealPlan.family_id == family_id,
            MealPlan.date == target_date,
            MealPlan.meal_type == body.meal_type,
        ).order_by(MealPlan.created_at.desc()).limit(1)
    )
    existing = existing_q.scalar_one_or_none()

    if existing:
        existing.selected_meal = body.dish_name
        existing.dishes = body.dishes
        existing.finalized_by_proxy = body.finalized_by_proxy
        plan = existing
    else:
        plan = MealPlan(
            family_id=family_id,
            date=target_date,
            meal_type=body.meal_type,
            selected_meal=body.dish_name,
            dishes=body.dishes,
            status=MealPlanStatus.PLANNED,
            finalized_by_proxy=body.finalized_by_proxy,
        )
        db.add(plan)

    # Auto-attach the family's default recipe (newest wins). For an
    # update where the dish drifted, the service clears the stale pin
    # and re-resolves; for a fresh insert, it pins if a default exists.
    # No-op if the plan has already been locked (cook briefed).
    try:
        from app.services.recipe_link_service import attach_recipe_to_plan
        await attach_recipe_to_plan(plan=plan, db=db)
    except Exception:  # noqa: BLE001 — recipe pinning must not break vote lock
        logger.exception("recipe_link auto-attach failed for plan")

    await db.commit()
    await db.refresh(plan)

    # Analytics — log the finalisation with InstaCook dimensions before
    # we kick off the (best-effort) ingredient-check side-effect.
    try:
        from app.routers.meals import _resolve_dish_taxonomy
        from app.services.analytics import track

        cuisine, is_veg = await _resolve_dish_taxonomy(body.dish_name, db)
        await track(
            "plan.finalized",
            family_id=family_id,
            actor_type="bimi" if body.finalized_by_proxy else "child",
            properties={
                "dish": body.dish_name,
                "cuisine": cuisine,
                "is_veg": is_veg,
                "meal_type": body.meal_type,
                "meal_date": target_date_str,
                "dish_count": len(body.dishes),
                "finalized_by_proxy": body.finalized_by_proxy,
                "is_update": existing is not None,
            },
            db=db,
        )
    except Exception:  # noqa: BLE001
        logger.exception("analytics.track(plan.finalized) failed")

    try:
        from sqlalchemy import select as sa_select

        from app.models.family import Family, Parent
        from app.services.ingredient_check import initiate_ingredient_check

        family_result = await db.execute(sa_select(Family).where(Family.id == family_id))
        family = family_result.scalar_one_or_none()
        cook_phone = family.cook_whatsapp if family and hasattr(family, "cook_whatsapp") and family.cook_whatsapp else None

        if not cook_phone:
            parents_result = await db.execute(sa_select(Parent).where(Parent.family_id == family_id))
            for parent in parents_result.scalars().all():
                if hasattr(parent, "cook_phone") and parent.cook_phone:
                    cook_phone = parent.cook_phone
                    break

        if cook_phone:
            await initiate_ingredient_check(
                family_id=family_id,
                meal_name=body.dish_name,
                meal_type=body.meal_type,
                meal_date=target_date_str,
                cook_phone=cook_phone,
                db=db,
            )
    except Exception:
        logger.exception("Ingredient check initiation failed (non-blocking)")

    return {
        "status": "finalized",
        "date": target_date_str,
        "meal_type": body.meal_type,
        "selected_meal": body.dish_name,
        "dishes": body.dishes,
        "finalized_by_proxy": body.finalized_by_proxy,
    }


@router.post("/families/{family_id}/dish-suggestions", response_model=SuggestionOut)
async def create_dish_suggestion(
    family_id: uuid.UUID,
    body: DishSuggestionRequest,
    db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access),
):
    """
    Submit a user-suggested dish with an optional video link.

    Extracts metadata from the link (YouTube/Instagram/other), infers
    ingredients via GPT, archives the recipe source, and returns an
    enriched suggestion ready for the voting pool.
    """
    from app.services.link_extractor import extract_metadata
    from app.services.meal_engine import infer_dish_details

    link_meta = None
    if body.source_url:
        link_meta = await extract_metadata(body.source_url)

    meta_dict = None
    if link_meta:
        meta_dict = {
            "title": link_meta.title,
            "author": link_meta.author,
            "description": link_meta.description,
        }

    details = await infer_dish_details(
        dish_name=body.dish_name,
        link_metadata=meta_dict,
    )

    if body.source_url and link_meta:
        recipe = RecipeSource(
            family_id=family_id,
            dish_name=body.dish_name,
            youtube_url=body.source_url,
            channel_name=link_meta.author,
            video_title=link_meta.title,
            source_platform=link_meta.platform,
            thumbnail_url=link_meta.thumbnail_url,
            description=link_meta.description,
            note_for_cook=body.note_for_cook,
            contributed_by_id=body.suggested_by_id,
            contributed_by_name=body.suggested_by_name,
            contributed_by_role="member",
            ingredients_extracted={"items": details.get("ingredients", [])},
            prep_notes_extracted=details.get("advance_prep_note"),
            is_default=True,
        )
        db.add(recipe)
        await db.commit()
        await db.refresh(recipe)

    constraints = details.get("constraints", [])
    for c in constraints:
        c.setdefault("memberName", "")
        c.setdefault("type", "health")
        c.setdefault("severity", "warning")

    suggestion_id = f"custom-{uuid.uuid4().hex[:8]}"

    return SuggestionOut(
        id=suggestion_id,
        dish_name=body.dish_name,
        confidence=0.7,
        fairness_score=0.5,
        novelty_bonus=1.0,
        prep_time=details.get("prep_time", "30 min"),
        needs_advance_prep=details.get("needs_advance_prep", False),
        advance_prep_note=details.get("advance_prep_note"),
        constraints=constraints,
        ingredients=details.get("ingredients", []),
        missing_ingredients=[],
        source_url=body.source_url,
        source_platform=link_meta.platform if link_meta else None,
        source_thumbnail=link_meta.thumbnail_url if link_meta else None,
        suggested_by_id=body.suggested_by_id,
        suggested_by_name=body.suggested_by_name,
        note_for_cook=body.note_for_cook,
    )
