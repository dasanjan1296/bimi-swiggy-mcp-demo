"""
Two-basket router for the meal-driven grocery flow.

Replaces the previous "create one Cart per missing-ingredient meal"
pattern in meal_preplanning.py with:

  1. Classify items as bulk vs perishable (services/grocery_classifier).
  2. Bulk items append to the family's open WeeklyBasket. No order is
     placed — the basket is checked out by the user via deep link on
     `family.weekly_bulk_day` (handled by weekly_basket_flow.py).
  3. Perishable items append to the family's open TopupBasket. The
     basket has a forced batching window so other meals' emerging
     needs can join the same delivery. When the window is ready to
     close AND the economics gate passes, the dispatcher places the
     order on the best UPI-capable platform.

This module is the central choke-point for grocery economics. If you
want to change how Bimi spends money on groceries, change this file.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.family import Family
from app.models.grocery_basket import (
    TopupBasket,
    TopupBasketStatus,
    TopupPaymentStatus,
    WeeklyBasket,
    WeeklyBasketStatus,
)
from app.services import grocery_economics
from app.services.grocery_classifier import GroceryCategory, classify_many
from app.services.mcp_ordering import dispatcher, pick_best_platform

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def route_missing_ingredients(
    family_id: uuid.UUID,
    missing_items: list[dict],
    *,
    earliest_meal_at: datetime | None,
    triggered_by_meal_plan_id: uuid.UUID | None,
    db: AsyncSession,
) -> dict:
    """Classify missing items and append them to the appropriate baskets.

    Returns a summary dict the caller (preplan scheduler) can log:
        {
          "weekly_added": 4,
          "weekly_basket_id": "...",
          "topup_added": 2,
          "topup_basket_id": "...",
          "topup_economics": {...},
          "topup_placed": False,
        }
    """
    if not missing_items:
        return {"weekly_added": 0, "topup_added": 0}

    hours_until = None
    if earliest_meal_at:
        hours_until = (earliest_meal_at - datetime.now(UTC)).total_seconds() / 3600

    buckets = classify_many(missing_items, hours_until_needed=hours_until)
    bulk_items = buckets[GroceryCategory.STAPLE_BULK]
    topup_items = buckets[GroceryCategory.PERISHABLE_TOPUP]

    family = await db.get(Family, family_id)

    summary: dict = {
        "weekly_added": 0,
        "topup_added": 0,
        "topup_placed": False,
    }

    # ---- Weekly bulk basket ----
    if bulk_items:
        wb = await _ensure_weekly_basket(family_id, family, db)
        merged = _merge_items(wb.items, bulk_items)
        wb.items = merged
        wb.estimated_total = _estimate_total(merged)
        summary["weekly_added"] = len(bulk_items)
        summary["weekly_basket_id"] = str(wb.id)

    # ---- Top-up perishable basket ----
    if topup_items:
        tb = await _ensure_topup_basket(family_id, earliest_meal_at, db)
        merged = _merge_items(tb.items, topup_items)
        tb.items = merged
        # Track which meal plans this basket is serving for ROI/audit
        ids = list(tb.triggered_by_meal_plan_ids or [])
        if triggered_by_meal_plan_id and str(triggered_by_meal_plan_id) not in ids:
            ids.append(str(triggered_by_meal_plan_id))
            tb.triggered_by_meal_plan_ids = ids

        summary["topup_added"] = len(topup_items)
        summary["topup_basket_id"] = str(tb.id)

        # Try to place the order if the window is ready and the economics gate passes
        place_outcome = await _try_place_topup(family, tb, db)
        summary["topup_placed"] = place_outcome.get("placed", False)
        summary["topup_reason"] = place_outcome.get("reason")
        summary["topup_economics"] = place_outcome.get("economics")

    await db.flush()
    return summary


# ---------------------------------------------------------------------------
# Weekly basket helpers
# ---------------------------------------------------------------------------


WEEKDAY_MAP = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def _next_weekday_after(today: date, weekday_name: str) -> date:
    target = WEEKDAY_MAP.get(weekday_name.lower(), 6)  # default sunday
    days_ahead = (target - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)


async def _ensure_weekly_basket(
    family_id: uuid.UUID,
    family: Family | None,
    db: AsyncSession,
) -> WeeklyBasket:
    result = await db.execute(
        select(WeeklyBasket).where(
            and_(
                WeeklyBasket.family_id == family_id,
                WeeklyBasket.status == WeeklyBasketStatus.COLLECTING.value,
            )
        )
    )
    basket = result.scalar_one_or_none()
    if basket:
        return basket

    target_day = (
        _next_weekday_after(date.today(), family.weekly_bulk_day)
        if family else None
    )
    basket = WeeklyBasket(
        family_id=family_id,
        status=WeeklyBasketStatus.COLLECTING.value,
        target_delivery_day=target_day,
    )
    basket.items = []
    db.add(basket)
    await db.flush()
    return basket


# ---------------------------------------------------------------------------
# Top-up basket helpers
# ---------------------------------------------------------------------------


async def _ensure_topup_basket(
    family_id: uuid.UUID,
    earliest_meal_at: datetime | None,
    db: AsyncSession,
) -> TopupBasket:
    result = await db.execute(
        select(TopupBasket).where(
            and_(
                TopupBasket.family_id == family_id,
                TopupBasket.status == TopupBasketStatus.COLLECTING.value,
            )
        )
    )
    basket = result.scalar_one_or_none()
    if basket:
        # Tighten the close window if a new earlier-need meal joins the basket.
        if earliest_meal_at:
            new_open, new_close = grocery_economics.batch_window(earliest_meal_at)
            if basket.batch_window_close_at is None or new_close < basket.batch_window_close_at:
                basket.batch_window_close_at = new_close
        return basket

    open_at = datetime.now(UTC)
    close_at = None
    if earliest_meal_at:
        open_at, close_at = grocery_economics.batch_window(earliest_meal_at)

    basket = TopupBasket(
        family_id=family_id,
        status=TopupBasketStatus.COLLECTING.value,
        batch_window_open_at=open_at,
        batch_window_close_at=close_at,
    )
    basket.items = []
    db.add(basket)
    await db.flush()
    return basket


async def _try_place_topup(
    family: Family | None,
    basket: TopupBasket,
    db: AsyncSession,
) -> dict:
    """Attempt to fire the top-up order if the batching window is closing
    and the economic guardrails pass.
    """
    now = datetime.now(UTC)

    if basket.batch_window_close_at and not grocery_economics.is_window_ready_to_close(
        now, basket.batch_window_close_at
    ):
        return {
            "placed": False,
            "reason": "batching_window_open",
            "close_at": basket.batch_window_close_at.isoformat(),
        }

    items = basket.items
    if not items:
        return {"placed": False, "reason": "empty_basket"}

    # Pick the best UPI-capable platform the family has connected.
    platform_id = await pick_best_platform(items, basket.family_id, db)
    if not platform_id:
        # No connected UPI platform — flip to AWAITING_APPROVAL so the
        # one-tap approval card surfaces in the app.
        basket.status = TopupBasketStatus.AWAITING_APPROVAL.value
        basket.failure_reason = "no_upi_platform_connected"
        return {"placed": False, "reason": "no_upi_platform_connected"}

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
            "economics": _economics_to_dict(economics),
        }

    # Auto-approval gate: cart_total <= family.auto_approve_threshold (legacy
    # column already on Family). If not, surface for approval.
    threshold = family.auto_approve_threshold if family else None
    if threshold is not None and cart_total > threshold:
        basket.status = TopupBasketStatus.AWAITING_APPROVAL.value
        basket.failure_reason = "above_auto_approve_threshold"
        return {
            "placed": False,
            "reason": "above_auto_approve_threshold",
            "economics": _economics_to_dict(economics),
        }

    # All gates passed — fire the UPI auto-order.
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
        try:
            from app.services.analytics import track as _track
            await _track(
                "topup_basket_placed",
                family_id=basket.family_id,
                actor_type="bimi",
                properties={
                    "basket_id": str(basket.id),
                    "platform_id": platform_id,
                    "cart_total": cart_total,
                    "delivery_fee": economics.delivery_fee,
                    "efficiency_ratio": round(economics.efficiency_ratio, 3),
                    "items_count": len(items),
                },
                db=db,
            )
        except Exception:
            logger.debug("analytics track skipped for topup_basket_placed")
        return {
            "placed": True,
            "platform_id": platform_id,
            "order_id": result.order_id,
            "economics": _economics_to_dict(economics),
        }

    basket.status = TopupBasketStatus.FAILED.value
    basket.failure_reason = result.error or "dispatcher_failed"
    try:
        from app.services.analytics import track as _track
        await _track(
            "topup_basket_failed",
            family_id=basket.family_id,
            actor_type="bimi",
            properties={
                "basket_id": str(basket.id),
                "platform_id": platform_id,
                "reason": basket.failure_reason,
            },
            db=db,
        )
    except Exception:
        logger.debug("analytics track skipped for topup_basket_failed")
    return {
        "placed": False,
        "reason": basket.failure_reason,
        "economics": _economics_to_dict(economics),
    }


# ---------------------------------------------------------------------------
# Item merging + price estimation
# ---------------------------------------------------------------------------


def _merge_items(existing: list[dict], new_items: list[dict]) -> list[dict]:
    """Merge new items into an existing basket list, summing quantities for
    duplicates by normalised name."""
    by_key: dict[str, dict] = {}
    for it in existing + new_items:
        key = (it.get("name", "") or "").strip().lower()
        if not key:
            continue
        if key in by_key:
            # sum quantity if present, else mark merged count
            try:
                by_key[key]["quantity"] = float(by_key[key].get("quantity", 1)) + float(it.get("quantity", 1))
            except (TypeError, ValueError):
                by_key[key]["quantity"] = it.get("quantity", 1)
        else:
            by_key[key] = dict(it)
    return list(by_key.values())


# Rough fallback prices (₹). Loop 5 will replace this with real Swiggy MCP
# product price lookups; until then the table keeps grocery_basket_router
# testable without a network call.
_FALLBACK_PRICES = {
    "milk": 60, "curd": 35, "paneer": 100, "bread": 40, "eggs": 80,
    "spinach": 30, "palak": 30, "tomato": 25, "onion": 30, "potato": 30,
    "atta": 250, "rice": 150, "dal": 180, "oil": 200, "ghee": 600,
    "salt": 25, "sugar": 50, "tea": 200, "biscuits": 50,
}


def _estimate_total(items: list[dict]) -> float:
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
            (price for token, price in _FALLBACK_PRICES.items() if token in name),
            50.0,
        )
        try:
            qty = float(it.get("quantity", 1) or 1)
        except (TypeError, ValueError):
            qty = 1.0
        total += token_price * max(qty, 1.0)
    return round(total, 2)


def _economics_to_dict(check) -> dict:
    return {
        "approved": check.approved,
        "reason": check.reason,
        "cart_total": check.cart_total,
        "delivery_fee": check.delivery_fee,
        "efficiency_ratio": round(check.efficiency_ratio, 3),
        "quota_remaining": check.quota_remaining,
    }
