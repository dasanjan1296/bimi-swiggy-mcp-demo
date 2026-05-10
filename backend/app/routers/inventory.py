"""Kitchen inventory management API."""

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.family import Child
from app.models.inventory import InventoryItem
from app.services.auth import get_current_child
from app.services.inventory import (
    get_inventory,
    get_low_stock_items,
    restock_from_cart,
    upsert_inventory_item,
)

router = APIRouter(prefix="/inventory", tags=["inventory"])


class InventoryItemOut(BaseModel):
    id: uuid.UUID
    item_name: str
    brand: str | None = None
    quantity_remaining: float
    unit: str
    is_staple: bool
    category: str
    estimated_depletion_rate: float | None = None

    model_config = {"from_attributes": True}


class InventoryItemCreate(BaseModel):
    item_name: str
    brand: str | None = None
    quantity_remaining: float = 0.0
    unit: str = "units"
    is_staple: bool = False
    category: str = "other"


class InventoryItemUpdate(BaseModel):
    item_name: str | None = None
    brand: str | None = None
    quantity_remaining: float | None = None
    unit: str | None = None
    is_staple: bool | None = None
    category: str | None = None


class RestockItem(BaseModel):
    # Loop 12 input validation:
    # - name must be non-empty (empty names match every fuzzy lookup
    #   and corrupt future restocks)
    # - quantity must be positive AND bounded (negative values
    #   would silently DRAIN inventory; absurdly-large values would
    #   poison aggregations)
    name: str = Field(min_length=1, max_length=255)
    brand: str | None = Field(default=None, max_length=255)
    quantity: float = Field(default=1.0, gt=0, lt=1e7)
    unit: str = Field(default="units", max_length=50)
    category: str = Field(default="other", max_length=50)


class RestockRequest(BaseModel):
    # Cap the list size to prevent a single request from spamming the
    # DB with thousands of inserts.
    items: list[RestockItem] = Field(min_length=1, max_length=200)


@router.get("", response_model=list[InventoryItemOut])
async def list_inventory(
    current_child: Child = Depends(get_current_child),
    db: AsyncSession = Depends(get_db),
):
    items = await get_inventory(current_child.family_id, db)
    return items


@router.get("/low-stock", response_model=list[InventoryItemOut])
async def list_low_stock(
    threshold_days: float = 3.0,
    current_child: Child = Depends(get_current_child),
    db: AsyncSession = Depends(get_db),
):
    items = await get_low_stock_items(current_child.family_id, db, threshold_days)
    return items


@router.post("", response_model=InventoryItemOut)
async def create_inventory_item(
    data: InventoryItemCreate,
    current_child: Child = Depends(get_current_child),
    db: AsyncSession = Depends(get_db),
):
    item = await upsert_inventory_item(
        current_child.family_id, data.model_dump(), db
    )
    await db.commit()
    return item


@router.put("/{item_id}", response_model=InventoryItemOut)
async def update_inventory_item(
    item_id: uuid.UUID,
    data: InventoryItemUpdate,
    current_child: Child = Depends(get_current_child),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(InventoryItem).where(
            and_(InventoryItem.id == item_id, InventoryItem.family_id == current_child.family_id)
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Inventory item not found")

    update_data = data.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        if v is not None:
            setattr(item, k, v)

    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/{item_id}")
async def delete_inventory_item(
    item_id: uuid.UUID,
    current_child: Child = Depends(get_current_child),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(InventoryItem).where(
            and_(InventoryItem.id == item_id, InventoryItem.family_id == current_child.family_id)
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Inventory item not found")

    await db.delete(item)
    await db.commit()
    return {"status": "deleted"}


@router.post("/restock", response_model=list[InventoryItemOut])
async def restock(
    data: RestockRequest,
    current_child: Child = Depends(get_current_child),
    db: AsyncSession = Depends(get_db),
):
    cart_items = [item.model_dump() for item in data.items]
    updated = await restock_from_cart(current_child.family_id, cart_items, db)
    await db.commit()
    return updated
