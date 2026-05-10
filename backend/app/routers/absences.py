"""Househelp absence management and replacement booking API."""

import logging
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.family import Child, Parent
from app.models.meal import HousehelpAbsence
from app.services.absence import (
    book_replacement,
    create_absence_from_client,
    get_absences,
    update_absence_fallback,
)
from app.services.auth import get_current_child, require_entity_access
from app.services.platforms import get_replacement_options

logger = logging.getLogger("bimi")
router = APIRouter(prefix="/absences", tags=["absences"])

ALLOWED_MEALS = {"breakfast", "lunch", "dinner"}
# Mirror of frontend `CookAbsenceFallback` in `app/lib/types.ts`. Validated
# at the API layer instead of via a Postgres ENUM so adding new values
# never requires a schema migration.
ALLOWED_FALLBACKS = {
    "order_food",
    "self_cook",
    "replacement_cook",
    "instacook",
    "skip",
}


class AbsenceOut(BaseModel):
    id: uuid.UUID
    family_id: uuid.UUID
    parent_id: uuid.UUID
    cook_name: str | None = None
    date: date
    end_date: date | None = None
    affected_meals: list[str] | None = None
    reason: str | None = None
    fallback_chosen: str | None = None
    fallback_details: str | None = None
    replacement_booked: bool
    replacement_platform: str | None = None
    replacement_deep_link: str | None = None
    sync_source: str | None = None

    model_config = {"from_attributes": True}


class AbsenceWithHousehelp(AbsenceOut):
    househelp_name: str | None = None
    househelp_role: str | None = None


class AbsenceCreateIn(BaseModel):
    parent_id: uuid.UUID
    date: date
    end_date: date | None = None
    affected_meals: list[str] | None = None
    reason: str | None = None

    @field_validator("affected_meals")
    @classmethod
    def _validate_meals(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        invalid = set(v) - ALLOWED_MEALS
        if invalid:
            raise ValueError(f"affected_meals contains invalid values: {sorted(invalid)}")
        return v

    @field_validator("end_date")
    @classmethod
    def _validate_end(cls, v: date | None, info) -> date | None:
        if v is None:
            return v
        start = info.data.get("date")
        if start is not None and v < start:
            raise ValueError("end_date must be >= date")
        return v


class AbsenceFallbackIn(BaseModel):
    fallback_chosen: str | None = None  # None to clear
    fallback_details: str | None = None

    @field_validator("fallback_chosen")
    @classmethod
    def _validate_fallback(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in ALLOWED_FALLBACKS:
            raise ValueError(
                f"fallback_chosen must be one of {sorted(ALLOWED_FALLBACKS)}"
            )
        return v


class BookReplacementRequest(BaseModel):
    platform_id: str


@router.get("", response_model=list[AbsenceOut])
async def list_absences(
    days: int = 30,
    current_child: Child = Depends(get_current_child),
    db: AsyncSession = Depends(get_db),
):
    """Return absences for the family, enriched with `cook_name` from
    the `parents` join so the mobile app can render them without a
    second round-trip per row."""
    since = date.today() - timedelta(days=days)
    result = await db.execute(
        select(HousehelpAbsence, Parent.name)
        .join(Parent, HousehelpAbsence.parent_id == Parent.id)
        .where(
            HousehelpAbsence.family_id == current_child.family_id,
            HousehelpAbsence.date >= since,
        )
        .order_by(HousehelpAbsence.date.desc())
    )
    out: list[AbsenceOut] = []
    for absence, cook_name in result.all():
        item = AbsenceOut.model_validate(absence)
        item.cook_name = cook_name
        out.append(item)
    return out


@router.post("", response_model=AbsenceOut, status_code=201)
async def create_absence(
    data: AbsenceCreateIn,
    current_child: Child = Depends(get_current_child),
    db: AsyncSession = Depends(get_db),
):
    """Client-driven absence creation from the mobile app.

    Distinct from the WhatsApp ingestion path (`record_absence` called
    from the webhook) — no WhatsApp message back to the cook, no
    push-notification fan-out (the next 30s `useLiveSync` poll on each
    device picks it up). Idempotent on (parent_id, date)."""
    parent = (
        await db.execute(select(Parent).where(Parent.id == data.parent_id))
    ).scalar_one_or_none()
    if not parent:
        raise HTTPException(status_code=404, detail="Parent not found")
    require_entity_access(current_child, parent)

    absence = await create_absence_from_client(
        parent,
        db,
        absence_date=data.date,
        end_date=data.end_date,
        affected_meals=data.affected_meals,
        reason=data.reason,
    )
    await db.commit()
    await db.refresh(absence)

    out = AbsenceOut.model_validate(absence)
    out.cook_name = parent.name
    return out


@router.patch("/{absence_id}/fallback", response_model=AbsenceOut)
async def patch_absence_fallback(
    absence_id: uuid.UUID,
    data: AbsenceFallbackIn,
    current_child: Child = Depends(get_current_child),
    db: AsyncSession = Depends(get_db),
):
    """Set or clear the household's fallback choice for an absence.
    Sending `fallback_chosen=None` un-resolves the absence so the
    picker re-appears on every device."""
    pre = (
        await db.execute(
            select(HousehelpAbsence).where(HousehelpAbsence.id == absence_id)
        )
    ).scalar_one_or_none()
    if not pre:
        raise HTTPException(status_code=404, detail="Absence not found")
    require_entity_access(current_child, pre)

    absence = await update_absence_fallback(
        absence_id,
        db,
        fallback_chosen=data.fallback_chosen,
        fallback_details=data.fallback_details,
    )
    await db.commit()
    await db.refresh(absence)

    parent_name = (
        await db.execute(select(Parent.name).where(Parent.id == absence.parent_id))
    ).scalar_one_or_none()
    out = AbsenceOut.model_validate(absence)
    out.cook_name = parent_name
    return out


@router.get("/today")
async def list_today_absences(
    current_child: Child = Depends(get_current_child),
    db: AsyncSession = Depends(get_db),
):
    """Get today's absences with househelp details and replacement options."""
    today = date.today()
    result = await db.execute(
        select(HousehelpAbsence, Parent)
        .join(Parent, HousehelpAbsence.parent_id == Parent.id)
        .where(
            HousehelpAbsence.family_id == current_child.family_id,
            HousehelpAbsence.date == today,
        )
    )
    rows = result.all()

    items = []
    for absence, parent in rows:
        options = get_replacement_options(parent.role) if parent.role != "parent" else []
        items.append({
            "absence": AbsenceOut.model_validate(absence),
            "househelp_name": parent.name,
            "househelp_role": parent.role,
            "replacement_options": options,
        })
    return items


@router.get("/upcoming")
async def list_upcoming_absences(
    current_child: Child = Depends(get_current_child),
    db: AsyncSession = Depends(get_db),
):
    """Get upcoming (advance-notice) absences with slot monitoring status."""
    today = date.today()
    result = await db.execute(
        select(HousehelpAbsence, Parent)
        .join(Parent, HousehelpAbsence.parent_id == Parent.id)
        .where(
            HousehelpAbsence.family_id == current_child.family_id,
            HousehelpAbsence.date > today,
            HousehelpAbsence.is_advance_notice.is_(True),
        )
        .order_by(HousehelpAbsence.date)
    )
    rows = result.all()

    items = []
    for absence, parent in rows:
        options = get_replacement_options(parent.role) if parent.role != "parent" else []
        items.append({
            "absence": AbsenceOut.model_validate(absence),
            "househelp_name": parent.name,
            "househelp_role": parent.role,
            "days_until": (absence.date - today).days,
            "slot_check_active": absence.slot_check_active,
            "slot_check_count": absence.slot_check_count,
            "slot_found": absence.slot_found_at is not None,
            "replacement_options": options,
        })
    return items


@router.post("/{absence_id}/book-replacement")
async def book_replacement_endpoint(
    absence_id: uuid.UUID,
    data: BookReplacementRequest,
    current_child: Child = Depends(get_current_child),
    db: AsyncSession = Depends(get_db),
):
    pre_check = await db.execute(
        select(HousehelpAbsence).where(HousehelpAbsence.id == absence_id)
    )
    absence_obj = pre_check.scalar_one_or_none()
    if not absence_obj:
        raise HTTPException(status_code=404, detail="Absence not found")
    require_entity_access(current_child, absence_obj)

    # Single-click booking via Urban Company removed with the multi-platform
    # retirement. The only "replacement" the system surfaces today is "order
    # food via Swiggy", which is rendered as a deep link in the app — no
    # backend booking flow.
    absence = await book_replacement(absence_id, data.platform_id, db)
    if not absence:
        raise HTTPException(status_code=404, detail="Absence not found")

    await db.commit()

    # Analytics — captures the household's fallback preference signal
    # for the InstaCook profile pipeline. "When the cook is off, what
    # do we tend to choose?" is a strong predictor of how InstaCook
    # offers should be ranked.
    try:
        from app.services.analytics import track
        await track(
            "cook.fallback_chosen",
            family_id=current_child.family_id,
            actor_type="child",
            actor_id=current_child.id,
            properties={
                "fallback": "order",
                "platform": data.platform_id,
                "absence_date": absence.date.isoformat(),
                "advance_notice": absence.is_advance_notice,
            },
            db=db,
        )
    except Exception:  # noqa: BLE001
        logger.exception("analytics.track(cook.fallback_chosen) failed")

    return {
        "status": "booked",
        "method": "deep_link",
        "platform": absence.replacement_platform,
        "deep_link": absence.replacement_deep_link,
    }
