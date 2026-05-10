import logging
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.guest import GuestProfile, GuestVisit
from app.services.auth import require_family_scoped_access
from app.models.family import Child

logger = logging.getLogger("bimi")
router = APIRouter(tags=["guests"])


class GuestProfileCreate(BaseModel):
    name: str
    dietary_type: str | None = None
    allergies: list[str] | None = None
    health_conditions: list[str] | None = None
    notes: str | None = None


class GuestVisitCreate(BaseModel):
    guest_name: str
    guest_profile_id: str | None = None
    meal_date: str
    meal_type: str
    head_count: int = 1
    dietary_constraints: dict | None = None


class GuestProfileOut(BaseModel):
    id: str
    name: str
    dietary_type: str | None = None
    allergies: list[str] | None = None
    health_conditions: list[str] | None = None
    notes: str | None = None
    visit_count: int = 0
    last_visit: str | None = None

    class Config:
        from_attributes = True


class GuestVisitOut(BaseModel):
    id: str
    guest_name: str
    meal_date: str
    meal_type: str
    head_count: int
    dietary_constraints: dict | None = None
    is_active: bool = True


@router.get("/families/{family_id}/guests", response_model=list[GuestProfileOut])
async def list_guest_profiles(family_id: uuid.UUID, db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    result = await db.execute(
        select(GuestProfile).where(GuestProfile.family_id == family_id).order_by(GuestProfile.last_visit.desc().nullslast())
    )
    profiles = result.scalars().all()
    return [
        GuestProfileOut(
            id=str(g.id), name=g.name, dietary_type=g.dietary_type,
            allergies=g.allergies, health_conditions=g.health_conditions,
            notes=g.notes, visit_count=g.visit_count,
            last_visit=str(g.last_visit) if g.last_visit else None,
        )
        for g in profiles
    ]


@router.post("/families/{family_id}/guests", response_model=GuestProfileOut)
async def create_guest_profile(family_id: uuid.UUID, body: GuestProfileCreate, db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    guest = GuestProfile(
        family_id=family_id,
        name=body.name,
        dietary_type=body.dietary_type,
        allergies=body.allergies,
        health_conditions=body.health_conditions,
        notes=body.notes,
    )
    db.add(guest)
    await db.commit()
    await db.refresh(guest)
    return GuestProfileOut(
        id=str(guest.id), name=guest.name, dietary_type=guest.dietary_type,
        allergies=guest.allergies, health_conditions=guest.health_conditions,
        notes=guest.notes, visit_count=0,
    )


@router.post("/families/{family_id}/guests/visits", response_model=GuestVisitOut)
async def add_guest_visit(family_id: uuid.UUID, body: GuestVisitCreate, db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    visit = GuestVisit(
        family_id=family_id,
        guest_name=body.guest_name,
        guest_profile_id=uuid.UUID(body.guest_profile_id) if body.guest_profile_id else None,
        meal_date=date.fromisoformat(body.meal_date),
        meal_type=body.meal_type,
        head_count=body.head_count,
        dietary_constraints=body.dietary_constraints,
    )
    db.add(visit)

    if body.guest_profile_id:
        result = await db.execute(select(GuestProfile).where(GuestProfile.id == uuid.UUID(body.guest_profile_id)))
        profile = result.scalar_one_or_none()
        if profile:
            profile.visit_count += 1
            profile.last_visit = date.fromisoformat(body.meal_date)

    await db.commit()
    await db.refresh(visit)
    return GuestVisitOut(
        id=str(visit.id), guest_name=visit.guest_name,
        meal_date=str(visit.meal_date), meal_type=visit.meal_type,
        head_count=visit.head_count, dietary_constraints=visit.dietary_constraints,
    )


@router.get("/families/{family_id}/guests/visits/{meal_date}", response_model=list[GuestVisitOut])
async def list_visits_for_date(family_id: uuid.UUID, meal_date: str, db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    result = await db.execute(
        select(GuestVisit).where(
            GuestVisit.family_id == family_id,
            GuestVisit.meal_date == date.fromisoformat(meal_date),
            GuestVisit.is_active == True,
        )
    )
    visits = result.scalars().all()
    return [
        GuestVisitOut(
            id=str(v.id), guest_name=v.guest_name,
            meal_date=str(v.meal_date), meal_type=v.meal_type,
            head_count=v.head_count, dietary_constraints=v.dietary_constraints,
        )
        for v in visits
    ]


@router.delete("/families/{family_id}/guests/visits/{visit_id}")
async def cancel_guest_visit(family_id: uuid.UUID, visit_id: uuid.UUID, db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    result = await db.execute(select(GuestVisit).where(GuestVisit.id == visit_id, GuestVisit.family_id == family_id))
    visit = result.scalar_one_or_none()
    if not visit:
        raise HTTPException(status_code=404, detail="Visit not found")
    visit.is_active = False
    await db.commit()
    return {"status": "cancelled"}
