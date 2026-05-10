"""Meal-history aggregation — server-side ground truth for the
past-meals calendar UI.

Joins three sources:
  - `meal_plans` (the finalised dish for a family/date/meal_type)
  - `meal_votes` (per-member votes, including AI proxy votes)
  - `meal_logs` (per-member feedback ratings)

Each output row is one (family, date, meal_type) combination — the
shape the FE `MealHistoryEntry` type expects. Members appear under
`participant_ids` if they voted OR rated for that meal.

Read path. Aggregator services (Phase 3) can also reuse this to feed
`family_dish_stats` and `member_preference_profile`.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date as date_t

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.meal import MealLog
from app.models.meal_plan import MealPlan
from app.models.vote import MealVote


# ── Output shapes ────────────────────────────────────────────────────


@dataclass
class HistoryVote:
    member_id: str
    member_name: str
    dish_name: str
    rating: int
    is_proxy: bool


@dataclass
class HistoryRating:
    member_id: str
    rating: int


@dataclass
class HistoryEntry:
    """One (family, date, meal_type) row. Mirrors the FE
    `MealHistoryEntry` type so the JSON serializes 1:1."""

    date: str  # yyyy-mm-dd
    meal_type: str
    selected_meal: str
    finalized_by_proxy: bool
    participant_ids: list[str] = field(default_factory=list)
    votes: list[HistoryVote] = field(default_factory=list)
    ratings: list[HistoryRating] = field(default_factory=list)


# ── Aggregator ───────────────────────────────────────────────────────


async def list_history(
    family_id: uuid.UUID,
    from_date: date_t,
    to_date: date_t,
    db: AsyncSession,
) -> list[HistoryEntry]:
    """Return the meal history for a family in [from_date, to_date].

    Inclusive on both ends. The output is ordered by (date desc,
    meal_type asc) — the calendar UI iterates per-cell so order
    doesn't matter, but stable ordering makes snapshot tests sane.

    Caps at 200 entries to keep responses bounded; callers should
    paginate via narrower date ranges if they need more.
    """
    plans_q = await db.execute(
        select(MealPlan).where(
            MealPlan.family_id == family_id,
            MealPlan.date >= from_date,
            MealPlan.date <= to_date,
        )
    )
    plans = list(plans_q.scalars().all())

    votes_q = await db.execute(
        select(MealVote).where(
            MealVote.family_id == family_id,
            MealVote.meal_date_d >= from_date,
            MealVote.meal_date_d <= to_date,
        )
    )
    votes = list(votes_q.scalars().all())

    logs_q = await db.execute(
        select(MealLog).where(
            MealLog.family_id == family_id,
            MealLog.date >= from_date,
            MealLog.date <= to_date,
        )
    )
    logs = list(logs_q.scalars().all())

    # Index helpers — avoid N quadratic scans below.
    votes_by_key: dict[tuple[str, str], list[MealVote]] = {}
    for v in votes:
        votes_by_key.setdefault(
            (v.meal_date_d.isoformat(), v.meal_type), []
        ).append(v)

    logs_by_key: dict[tuple[str, str], list[MealLog]] = {}
    for log in logs:
        logs_by_key.setdefault(
            (log.date.isoformat(), log.meal_type), []
        ).append(log)

    # Build one HistoryEntry per finalised plan. Dish is always the
    # plan.selected_meal; votes + ratings join on (date, meal_type).
    entries: list[HistoryEntry] = []
    for plan in plans:
        key = (plan.date.isoformat(), plan.meal_type)
        plan_votes = votes_by_key.get(key, [])
        plan_logs = logs_by_key.get(key, [])

        # Ratings: meal_logs.rating belongs to the household, not a
        # specific member, in the legacy schema. The new feedback
        # endpoint will write per-member rows. Until then we surface
        # the household-level rating as a single anonymous entry; a
        # follow-up migration will denormalise the per-member shape.
        ratings: list[HistoryRating] = []
        for log in plan_logs:
            if log.rating is not None:
                # Anonymous rating bucket — frontend renders this as
                # "household rated 4★" until per-member ratings land.
                ratings.append(HistoryRating(member_id="household", rating=log.rating))

        participant_ids = sorted({v.member_id for v in plan_votes})

        entries.append(
            HistoryEntry(
                date=plan.date.isoformat(),
                meal_type=plan.meal_type,
                selected_meal=plan.selected_meal,
                finalized_by_proxy=plan.finalized_by_proxy,
                participant_ids=participant_ids,
                votes=[
                    HistoryVote(
                        member_id=v.member_id,
                        member_name=v.member_name,
                        dish_name=v.dish_name,
                        rating=v.rating,
                        is_proxy=v.is_proxy,
                    )
                    for v in plan_votes
                ],
                ratings=ratings,
            )
        )

    # Stable ordering — most recent first.
    entries.sort(key=lambda e: (e.date, e.meal_type), reverse=True)
    return entries[:200]


__all__ = [
    "HistoryEntry",
    "HistoryRating",
    "HistoryVote",
    "list_history",
]
