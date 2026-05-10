"""Endpoints for the two-basket grocery system.

Surfaces:
  - GET /api/grocery/baskets/weekly       → current open weekly basket
  - POST /api/grocery/baskets/weekly/{id}/completed → user marks deep-link checkout done
  - GET /api/grocery/baskets/topup        → current open / awaiting-approval top-up
  - POST /api/grocery/baskets/topup/{id}/accept → one-tap approval to fire UPI order
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.family import Child
from app.models.grocery_basket import (
    TopupBasket,
    TopupBasketStatus,
    WeeklyBasket,
    WeeklyBasketStatus,
)
from app.services.auth import get_current_child
from app.services.topup_basket_flow import accept_topup
from app.services.weekly_basket_flow import mark_weekly_basket_completed

router = APIRouter(prefix="/grocery/baskets", tags=["grocery"])


class WeeklyBasketOut(BaseModel):
    id: uuid.UUID
    status: str
    item_count: int
    estimated_total: float
    platform_id: str | None = None
    deep_link_url: str | None = None
    target_delivery_day: str | None = None
    sent_at: datetime | None = None


class TopupBasketOut(BaseModel):
    id: uuid.UUID
    status: str
    item_count: int
    cart_total: float | None = None
    delivery_fee: float | None = None
    delivery_efficiency_ratio: float | None = None
    platform_id: str | None = None
    batch_window_close_at: datetime | None = None
    failure_reason: str | None = None
    payment_status: str
    placed_at: datetime | None = None
    tracking_url: str | None = None


class AcceptTopupResponse(BaseModel):
    basket_id: uuid.UUID
    status: str
    order_id: str | None = None
    reason: str | None = None


@router.get("/weekly", response_model=WeeklyBasketOut | None)
async def get_open_weekly_basket(
    current_child: Child = Depends(get_current_child),
    db: AsyncSession = Depends(get_db),
):
    """Return the current rolling weekly bulk basket (or the most recently
    sent one if there's no open basket). Returns null when nothing is queued.
    """
    result = await db.execute(
        select(WeeklyBasket)
        .where(WeeklyBasket.family_id == current_child.family_id)
        .where(WeeklyBasket.status.in_([
            WeeklyBasketStatus.COLLECTING.value,
            WeeklyBasketStatus.SENT_TO_USER.value,
        ]))
        .order_by(WeeklyBasket.created_at.desc())
    )
    basket = result.scalar_one_or_none()
    if not basket:
        return None
    return WeeklyBasketOut(
        id=basket.id,
        status=basket.status,
        item_count=len(basket.items),
        estimated_total=basket.estimated_total,
        platform_id=basket.platform_id,
        deep_link_url=basket.deep_link_url,
        target_delivery_day=basket.target_delivery_day.isoformat() if basket.target_delivery_day else None,
        sent_at=basket.sent_at,
    )


@router.post("/weekly/{basket_id}/completed", response_model=WeeklyBasketOut)
async def mark_weekly_completed(
    basket_id: uuid.UUID,
    current_child: Child = Depends(get_current_child),
    db: AsyncSession = Depends(get_db),
):
    basket = await db.get(WeeklyBasket, basket_id)
    if not basket or basket.family_id != current_child.family_id:
        raise HTTPException(status_code=404, detail="Weekly basket not found")
    basket = await mark_weekly_basket_completed(basket_id, db)
    await db.commit()
    return WeeklyBasketOut(
        id=basket.id,
        status=basket.status,
        item_count=len(basket.items),
        estimated_total=basket.estimated_total,
        platform_id=basket.platform_id,
        deep_link_url=basket.deep_link_url,
        target_delivery_day=basket.target_delivery_day.isoformat() if basket.target_delivery_day else None,
        sent_at=basket.sent_at,
    )


@router.get("/topup", response_model=TopupBasketOut | None)
async def get_open_topup_basket(
    current_child: Child = Depends(get_current_child),
    db: AsyncSession = Depends(get_db),
):
    """Return the current open / awaiting-approval top-up basket, or null."""
    result = await db.execute(
        select(TopupBasket)
        .where(TopupBasket.family_id == current_child.family_id)
        .where(TopupBasket.status.in_([
            TopupBasketStatus.COLLECTING.value,
            TopupBasketStatus.AWAITING_APPROVAL.value,
        ]))
        .order_by(TopupBasket.created_at.desc())
    )
    basket = result.scalar_one_or_none()
    if not basket:
        return None
    return TopupBasketOut(
        id=basket.id,
        status=basket.status,
        item_count=len(basket.items),
        cart_total=basket.cart_total,
        delivery_fee=basket.delivery_fee,
        delivery_efficiency_ratio=basket.delivery_efficiency_ratio,
        platform_id=basket.platform_id,
        batch_window_close_at=basket.batch_window_close_at,
        failure_reason=basket.failure_reason,
        payment_status=basket.payment_status,
        placed_at=basket.placed_at,
        tracking_url=basket.tracking_url,
    )


@router.post("/topup/{basket_id}/accept", response_model=AcceptTopupResponse)
async def accept_topup_endpoint(
    basket_id: uuid.UUID,
    current_child: Child = Depends(get_current_child),
    db: AsyncSession = Depends(get_db),
):
    """User taps Approve & Pay on the one-tap card."""
    basket = await db.get(TopupBasket, basket_id)
    if not basket or basket.family_id != current_child.family_id:
        raise HTTPException(status_code=404, detail="Top-up basket not found")

    outcome = await accept_topup(basket_id, db)

    if outcome.get("status") in ("error", "failed"):
        raise HTTPException(status_code=409, detail=outcome.get("reason", "approval_failed"))

    return AcceptTopupResponse(
        basket_id=basket_id,
        status=outcome.get("status", "unknown"),
        order_id=outcome.get("order_id"),
        reason=outcome.get("reason"),
    )
