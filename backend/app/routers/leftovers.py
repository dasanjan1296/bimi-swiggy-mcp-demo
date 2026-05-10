import logging
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.leftover import Leftover
from app.services.auth import require_family_scoped_access
from app.models.family import Child

logger = logging.getLogger("bimi")
router = APIRouter(tags=["leftovers"])


class LeftoverCreate(BaseModel):
    dish_name: str
    meal_date: str
    meal_type: str
    portions_remaining: int = 1
    reported_by: str | None = None
    notes: str | None = None


class LeftoverOut(BaseModel):
    id: str
    dish_name: str
    meal_date: str
    meal_type: str
    portions_remaining: int
    is_consumed: bool
    is_disposed: bool
    is_safe: bool
    notes: str | None = None

    class Config:
        from_attributes = True


@router.get("/families/{family_id}/leftovers", response_model=list[LeftoverOut])
async def list_leftovers(family_id: uuid.UUID, active_only: bool = True, db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    query = select(Leftover).where(Leftover.family_id == family_id)
    if active_only:
        query = query.where(
            Leftover.is_consumed == False,
            Leftover.is_disposed == False,
            Leftover.meal_date >= date.today() - timedelta(days=1),
        )
    result = await db.execute(query.order_by(Leftover.meal_date.desc()))
    items = result.scalars().all()
    return [
        LeftoverOut(
            id=str(lo.id), dish_name=lo.dish_name, meal_date=str(lo.meal_date),
            meal_type=lo.meal_type, portions_remaining=lo.portions_remaining,
            is_consumed=lo.is_consumed, is_disposed=lo.is_disposed,
            is_safe=lo.is_safe, notes=lo.notes,
        )
        for lo in items
    ]


@router.post("/families/{family_id}/leftovers", response_model=LeftoverOut)
async def report_leftover(family_id: uuid.UUID, body: LeftoverCreate, db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    lo = Leftover(
        family_id=family_id,
        dish_name=body.dish_name,
        meal_date=date.fromisoformat(body.meal_date),
        meal_type=body.meal_type,
        portions_remaining=body.portions_remaining,
        reported_by=body.reported_by,
        notes=body.notes,
    )
    db.add(lo)
    await db.commit()
    await db.refresh(lo)
    return LeftoverOut(
        id=str(lo.id), dish_name=lo.dish_name, meal_date=str(lo.meal_date),
        meal_type=lo.meal_type, portions_remaining=lo.portions_remaining,
        is_consumed=lo.is_consumed, is_disposed=lo.is_disposed,
        is_safe=lo.is_safe, notes=lo.notes,
    )


@router.post("/families/{family_id}/leftovers/{leftover_id}/consume")
async def consume_leftover(family_id: uuid.UUID, leftover_id: uuid.UUID, db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    result = await db.execute(select(Leftover).where(Leftover.id == leftover_id, Leftover.family_id == family_id))
    lo = result.scalar_one_or_none()
    if not lo:
        raise HTTPException(status_code=404, detail="Leftover not found")
    lo.is_consumed = True
    lo.consumed_date = date.today()
    await db.commit()
    return {"status": "consumed"}


@router.post("/families/{family_id}/leftovers/{leftover_id}/dispose")
async def dispose_leftover(family_id: uuid.UUID, leftover_id: uuid.UUID, reason: str = "expired", db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    result = await db.execute(select(Leftover).where(Leftover.id == leftover_id, Leftover.family_id == family_id))
    lo = result.scalar_one_or_none()
    if not lo:
        raise HTTPException(status_code=404, detail="Leftover not found")
    lo.is_disposed = True
    lo.disposed_reason = reason
    await db.commit()
    return {"status": "disposed"}
