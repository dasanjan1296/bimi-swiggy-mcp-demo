"""Scheduled calls router — parent-child call coordination."""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.family import Child, Parent
from app.models.scheduled_call import ScheduledCall
from app.services.auth import require_family_scoped_access

router = APIRouter(tags=["calls"])


class CallCreate(BaseModel):
    family_id: uuid.UUID
    requester_id: uuid.UUID
    target_child_id: uuid.UUID | None = None
    requester_name: str
    target_name: str
    original_text: str = ""
    timeframe_hours: int = 48


class CallSchedule(BaseModel):
    scheduled_at: datetime


class CallOut(BaseModel):
    id: uuid.UUID
    family_id: uuid.UUID
    requester_id: uuid.UUID
    target_child_id: uuid.UUID | None
    requester_name: str
    target_name: str
    original_text: str
    timeframe_hours: int
    scheduled_at: datetime | None
    status: str
    reminder_sent: bool
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("/calls", response_model=list[CallOut])
async def list_calls(
    family_id: uuid.UUID,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    _child: Child = Depends(require_family_scoped_access)
):
    query = (
        select(ScheduledCall)
        .where(ScheduledCall.family_id == family_id)
        .order_by(ScheduledCall.created_at.desc())
        .limit(50)
    )
    if status:
        query = query.where(ScheduledCall.status == status)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/calls", response_model=CallOut, status_code=201)
async def create_call(body: CallCreate, db: AsyncSession = Depends(get_db)):
    # Pre-flight FK validation: scheduled_calls.requester_id has a hard FK to
    # parents.id. Without this check, a bad UUID 500s at COMMIT time with a
    # raw asyncpg ForeignKeyViolation — confusing to debug AND a leak of
    # internal schema. Surface a clean 400 instead.
    parent = await db.get(Parent, body.requester_id)
    if parent is None:
        raise HTTPException(
            status_code=400,
            detail="requester_id must reference an existing parent",
        )
    if parent.family_id != body.family_id:
        raise HTTPException(
            status_code=403,
            detail="requester does not belong to this family",
        )

    call = ScheduledCall(
        family_id=body.family_id,
        requester_id=body.requester_id,
        target_child_id=body.target_child_id,
        requester_name=body.requester_name,
        target_name=body.target_name,
        original_text=body.original_text,
        timeframe_hours=body.timeframe_hours,
    )
    db.add(call)
    try:
        await db.commit()
    except IntegrityError as exc:
        # Defence in depth: e.g. target_child_id FK or family_id FK could
        # also fail. Convert any FK violation to 400 rather than letting
        # the global 500 handler swallow it.
        await db.rollback()
        raise HTTPException(status_code=400, detail="invalid foreign key") from exc
    await db.refresh(call)
    return call


@router.post("/calls/{call_id}/schedule", response_model=CallOut)
async def schedule_call(
    call_id: uuid.UUID,
    body: CallSchedule,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ScheduledCall).where(ScheduledCall.id == call_id))
    call = result.scalar_one_or_none()
    if not call:
        raise HTTPException(404, "Call not found")
    if call.status not in ("requested", "rescheduled"):
        raise HTTPException(400, f"Cannot schedule a call in '{call.status}' status")
    call.scheduled_at = body.scheduled_at
    call.status = "scheduled"
    await db.commit()
    await db.refresh(call)
    return call


@router.post("/calls/{call_id}/complete", response_model=CallOut)
async def complete_call(
    call_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ScheduledCall).where(ScheduledCall.id == call_id))
    call = result.scalar_one_or_none()
    if not call:
        raise HTTPException(404, "Call not found")
    call.status = "completed"
    await db.commit()
    await db.refresh(call)
    return call


@router.post("/calls/{call_id}/reschedule", response_model=CallOut)
async def reschedule_call(
    call_id: uuid.UUID,
    body: CallSchedule | None = None,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ScheduledCall).where(ScheduledCall.id == call_id))
    call = result.scalar_one_or_none()
    if not call:
        raise HTTPException(404, "Call not found")
    call.status = "rescheduled"
    call.scheduled_at = body.scheduled_at if body else None
    call.reminder_sent = False
    await db.commit()
    await db.refresh(call)
    return call
