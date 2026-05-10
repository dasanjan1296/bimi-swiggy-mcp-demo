"""Cross-device meal-history API.

Backs the meals-history calendar in the mobile app — the past-day
modal reads from this endpoint so what one household member sees on
their phone matches what every other member sees on theirs.

Mounted at the root of `/api` (no router-level prefix) so the URL is
`/api/families/{family_id}/meal-history?from=&to=`. The shape mirrors
the FE `MealHistoryEntry` type exactly.

Aggregation logic lives in `services/meal_history.py` so the same
join can be reused by Phase 3 family-aggregator code without
duplicating SQL.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.family import Child
from app.services.auth import require_family_scoped_access
from app.services.meal_history import list_history


logger = logging.getLogger("bimi")
router = APIRouter(tags=["meal-history"])


class HistoryVoteOut(BaseModel):
    member_id: str
    member_name: str
    dish_name: str
    rating: int
    is_proxy: bool = False


class HistoryRatingOut(BaseModel):
    member_id: str
    rating: int


class HistoryEntryOut(BaseModel):
    date: str
    meal_type: str
    selected_meal: str
    finalized_by_proxy: bool = False
    participant_ids: list[str] = []
    votes: list[HistoryVoteOut] = []
    ratings: list[HistoryRatingOut] = []


@router.get(
    "/families/{family_id}/meal-history",
    response_model=list[HistoryEntryOut],
)
async def get_meal_history(
    family_id: uuid.UUID,
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access),
):
    """Server-side ground truth for the meals-history calendar.

    Returns all finalised meals in [from, to] inclusive. Defaults to
    the last 60 days when both query params are omitted; the span is
    hard-capped at 90 days so a misbehaving client can't ask for the
    entire history at once.
    """
    today = date.today()
    if to_date is None:
        to_date = today
    if from_date is None:
        from_date = to_date - timedelta(days=60)

    span = (to_date - from_date).days
    if span < 0:
        raise HTTPException(400, "from must be on or before to")
    if span > 90:
        from_date = to_date - timedelta(days=90)

    entries = await list_history(family_id, from_date, to_date, db)

    return [
        HistoryEntryOut(
            date=e.date,
            meal_type=e.meal_type,
            selected_meal=e.selected_meal,
            finalized_by_proxy=e.finalized_by_proxy,
            participant_ids=e.participant_ids,
            votes=[HistoryVoteOut(**v.__dict__) for v in e.votes],
            ratings=[HistoryRatingOut(**r.__dict__) for r in e.ratings],
        )
        for e in entries
    ]
