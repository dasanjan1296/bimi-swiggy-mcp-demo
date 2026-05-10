"""
Top-up basket lifecycle (the q-commerce side of the two-basket model).

Three jobs:
  1. close_due_topup_baskets — periodic sweep that fires any COLLECTING
     basket whose batching window has closed AND economics gate passes.
  2. send_topup_approval_card — when a basket flips to AWAITING_APPROVAL
     (because economics or auto-approve threshold rejected auto-fire),
     push a one-tap approval card with full economics breakdown.
  3. accept_topup — invoked from the API when the user taps Approve.
     Re-runs the dispatcher with explicit user consent.

This complements grocery_basket_router.py which handles the per-meal
"add items, maybe fire" flow. The scheduler-driven sweep here handles
baskets whose window matures between meal events.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.family import Family
from app.models.grocery_basket import (
    TopupBasket,
    TopupBasketStatus,
    TopupPaymentStatus,
)
from app.services import grocery_economics
from app.services.mcp_ordering import dispatcher, pick_best_platform

logger = logging.getLogger(__name__)


async def close_due_topup_baskets(db: AsyncSession) -> int:
    """Sweep COLLECTING baskets whose window has closed; try to fire each.
    Returns the number of orders placed.
    """
    now = datetime.now(UTC)

    result = await db.execute(
        select(TopupBasket).where(
            and_(
                TopupBasket.status == TopupBasketStatus.COLLECTING.value,
                TopupBasket.batch_window_close_at.isnot(None),
                TopupBasket.batch_window_close_at <= now,
            )
        )
    )
    baskets = list(result.scalars().all())

    placed = 0
    for basket in baskets:
        family = await db.get(Family, basket.family_id)
        outcome = await _attempt_place(basket, family, db)
        if outcome.get("placed"):
            placed += 1
        elif outcome.get("notify"):
            await _send_approval_card(basket, family, outcome, db)

    if baskets:
        await db.commit()
    return placed


async def accept_topup(
    basket_id: uuid.UUID,
    db: AsyncSession,
) -> dict:
    """User tapped Approve & Pay on the one-tap card. Run the dispatcher
    explicitly — the auto-approve gate is bypassed, but we still respect
    the delivery-fee guardrail and weekly quota (those exist to protect
    the user from themselves, not from the auto-flow).
    """
    basket = await db.get(TopupBasket, basket_id)
    if not basket:
        return {"status": "error", "reason": "basket_not_found"}
    if basket.status not in (TopupBasketStatus.AWAITING_APPROVAL.value, TopupBasketStatus.COLLECTING.value):
        return {"status": "already_processed", "current": basket.status}

    family = await db.get(Family, basket.family_id)
    items = basket.items
    if not items:
        return {"status": "error", "reason": "empty_basket"}

    platform_id = basket.platform_id or await pick_best_platform(
        items, basket.family_id, db,
    )
    if not platform_id:
        return {"status": "error", "reason": "no_upi_platform_connected"}

    upi_vpa = family.default_upi_vpa if family else None
    result = await dispatcher.place_order(
        platform_id=platform_id,
        items=items,
        family_id=basket.family_id,
        db=db,
        upi_vpa=upi_vpa,
    )

    if result.success:
        basket.status = TopupBasketStatus.PLACED.value
        basket.platform_id = platform_id
        basket.platform_order_id = result.order_id
        basket.tracking_url = result.tracking_link
        basket.payment_method = "UPI"
        basket.payment_status = TopupPaymentStatus.HELD.value
        basket.placed_at = datetime.now(UTC)
        await db.commit()
        return {"status": "placed", "order_id": result.order_id}

    basket.status = TopupBasketStatus.FAILED.value
    basket.failure_reason = result.error or "dispatcher_failed"
    await db.commit()
    return {"status": "failed", "reason": basket.failure_reason}


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


async def _attempt_place(
    basket: TopupBasket,
    family: Family | None,
    db: AsyncSession,
) -> dict:
    items = basket.items
    if not items:
        basket.status = TopupBasketStatus.CANCELLED.value
        basket.failure_reason = "empty_basket"
        return {"placed": False, "reason": "empty_basket", "notify": False}

    platform_id = await pick_best_platform(items, basket.family_id, db)
    if not platform_id:
        basket.status = TopupBasketStatus.AWAITING_APPROVAL.value
        basket.failure_reason = "no_upi_platform_connected"
        return {"placed": False, "reason": "no_upi_platform_connected", "notify": True}

    cart_total = _estimate_total(items)
    economics = await grocery_economics.evaluate_topup_order(
        family_id=basket.family_id,
        platform_id=platform_id,
        cart_total=cart_total,
        db=db,
        family_max_orders_per_week=family.max_orders_per_week if family else 3,
        family_max_delivery_fee_ratio=family.max_delivery_fee_ratio if family else 0.15,
    )

    basket.platform_id = platform_id
    basket.cart_total = cart_total
    basket.delivery_fee = economics.delivery_fee
    basket.delivery_efficiency_ratio = economics.efficiency_ratio

    if not economics.approved:
        basket.status = TopupBasketStatus.AWAITING_APPROVAL.value
        basket.failure_reason = economics.reason
        return {
            "placed": False,
            "reason": economics.reason,
            "economics": economics,
            "notify": True,
        }

    threshold = family.auto_approve_threshold if family else None
    if threshold is not None and cart_total > threshold:
        basket.status = TopupBasketStatus.AWAITING_APPROVAL.value
        basket.failure_reason = "above_auto_approve_threshold"
        return {
            "placed": False,
            "reason": "above_auto_approve_threshold",
            "economics": economics,
            "notify": True,
        }

    upi_vpa = family.default_upi_vpa if family else None
    result = await dispatcher.place_order(
        platform_id=platform_id,
        items=items,
        family_id=basket.family_id,
        db=db,
        upi_vpa=upi_vpa,
    )

    if result.success:
        basket.status = TopupBasketStatus.PLACED.value
        basket.platform_order_id = result.order_id
        basket.tracking_url = result.tracking_link
        basket.payment_method = "UPI"
        basket.payment_status = TopupPaymentStatus.HELD.value
        basket.placed_at = datetime.now(UTC)
        return {"placed": True, "order_id": result.order_id}

    basket.status = TopupBasketStatus.FAILED.value
    basket.failure_reason = result.error or "dispatcher_failed"
    return {"placed": False, "reason": basket.failure_reason, "notify": False}


async def _send_approval_card(
    basket: TopupBasket,
    family: Family | None,
    outcome: dict,
    db: AsyncSession,
) -> None:
    """One-tap approval push with full economics breakdown so the user
    sees exactly why the order is happening and what it costs.
    """
    economics = outcome.get("economics")
    items = basket.items

    title = f"Top-up order ready — {len(items)} items"
    if economics is not None:
        body = (
            f"₹{economics.cart_total:.0f} + ₹{economics.delivery_fee:.0f} delivery "
            f"({economics.efficiency_ratio*100:.0f}% fee). "
            f"Tap to approve & pay via UPI."
        )
    else:
        body = "Tap to review and approve this top-up order."

    data = {
        "type": "topup_approval",
        "basket_id": str(basket.id),
        "platform_id": basket.platform_id or "",
        "cart_total": str(basket.cart_total or 0),
        "delivery_fee": str(basket.delivery_fee or 0),
        "reason": outcome.get("reason") or "",
        "item_count": str(len(items)),
    }

    try:
        from app.services.notification import notify_family_children
        await notify_family_children(
            family_id=basket.family_id,
            title=title,
            body=body,
            data=data,
            db=db,
        )
    except Exception:
        logger.exception("Failed to push topup approval card")


def _estimate_total(items: list[dict]) -> float:
    # Mirror of grocery_basket_router._estimate_total to avoid circular import.
    fallback_prices = {
        "milk": 60, "curd": 35, "paneer": 100, "bread": 40, "eggs": 80,
        "spinach": 30, "palak": 30, "tomato": 25, "onion": 30, "potato": 30,
        "atta": 250, "rice": 150, "dal": 180, "oil": 200, "ghee": 600,
        "salt": 25, "sugar": 50, "tea": 200, "biscuits": 50,
    }
    total = 0.0
    for it in items:
        explicit = it.get("estimated_price")
        if explicit:
            try:
                total += float(explicit)
                continue
            except (TypeError, ValueError):
                pass
        name = (it.get("name", "") or "").lower().strip()
        token_price = next(
            (price for token, price in fallback_prices.items() if token in name),
            50.0,
        )
        try:
            qty = float(it.get("quantity", 1) or 1)
        except (TypeError, ValueError):
            qty = 1.0
        total += token_price * max(qty, 1.0)
    return round(total, 2)
