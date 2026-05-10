import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.context import ItemRejection
from app.models.family import Child
from app.schemas.context import FamilyContextOut, FamilyContextUpdate, ItemRejectionOut
from app.services.auth import get_current_child
from app.services.context_memory import get_or_create_family_context

router = APIRouter(prefix="/context", tags=["context"])


@router.get("/{family_id}", response_model=FamilyContextOut)
async def get_family_context(
    family_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_child: Child = Depends(get_current_child),
):
    ctx = await get_or_create_family_context(family_id, db)
    await db.commit()
    return ctx


@router.put("/{family_id}", response_model=FamilyContextOut)
async def update_family_context(
    family_id: uuid.UUID,
    body: FamilyContextUpdate,
    db: AsyncSession = Depends(get_db),
    current_child: Child = Depends(get_current_child),
):
    ctx = await get_or_create_family_context(family_id, db)

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(ctx, field, value)

    await db.commit()
    await db.refresh(ctx)
    return ctx


@router.get("/{family_id}/rejections", response_model=list[ItemRejectionOut])
async def list_rejections(
    family_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_child: Child = Depends(get_current_child),
):
    result = await db.execute(
        select(ItemRejection)
        .where(ItemRejection.family_id == family_id)
        .order_by(ItemRejection.rejection_count.desc())
        .limit(50)
    )
    return result.scalars().all()


@router.delete("/{family_id}/rejections/{rejection_id}")
async def clear_rejection(
    family_id: uuid.UUID,
    rejection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_child: Child = Depends(get_current_child),
):
    """Remove a rejection (e.g., family wants to try that brand again)."""
    result = await db.execute(
        select(ItemRejection).where(ItemRejection.id == rejection_id)
    )
    rejection = result.scalar_one_or_none()
    if not rejection:
        raise HTTPException(404, "Rejection not found")
    await db.delete(rejection)
    await db.commit()
    return {"status": "deleted"}
