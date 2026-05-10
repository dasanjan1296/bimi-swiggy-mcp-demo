"""Economic guardrails for grocery auto-ordering.

These pure functions are the single most important defense against
runaway delivery fees. The previous "one MCP order per meal" pattern
could rack up ~₹3,000/month in delivery fees alone for a typical
3-meals-a-day family. The rules here cap that.

All functions are pure (no I/O) so they're trivially unit-testable.
The `weekly_quota_remaining` helper takes a db session because it
needs to count placed top-up baskets in the last 7 days.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

# Sensible delivery-fee fallback for Swiggy Instamart (the only grocery
# platform after the multi-platform retirement). Conservative-high — better
# to over-estimate and skip a marginal order than to fire one that turns
# out to be 30% delivery fee at the till.
DEFAULT_DELIVERY_FEES_INR: dict[str, float] = {
    "swiggy_instamart": 30.0,
    # Swiggy Food (restaurant orders) carries higher per-order fees + GST,
    # quoted higher to discourage marginal "order food" suggestions.
    "swiggy_food": 50.0,
}

# Q-commerce platforms typically charge a "small order fee" if subtotal is
# below ~₹150-180. We treat anything under SMALL_ORDER_FLOOR as inefficient
# unless the items are flagged urgent.
SMALL_ORDER_FLOOR_INR = 150.0


@dataclass
class EconomicsCheck:
    """Outcome of running the economic guardrails on a candidate top-up order."""
    approved: bool
    reason: str
    cart_total: float
    delivery_fee: float
    efficiency_ratio: float
    quota_remaining: int


# ---------------------------------------------------------------------------
# Delivery efficiency
# ---------------------------------------------------------------------------

def delivery_efficiency(cart_total: float, delivery_fee: float, handling_fee: float = 0.0) -> float:
    """Returns (delivery + handling) / max(cart_total, 0.01).

    Rule of thumb: an "efficient" order has efficiency <= 0.15. At 0.20+
    the family is paying 1 rupee in fees for every 4 rupees of groceries.
    """
    if cart_total <= 0:
        return 1.0  # treat empty cart as maximally inefficient
    return (max(delivery_fee, 0.0) + max(handling_fee, 0.0)) / cart_total


def is_efficient_enough(ratio: float, family_max_ratio: float = 0.15) -> bool:
    """True if the delivery efficiency ratio is within the family's tolerance."""
    return ratio <= family_max_ratio


def estimate_delivery_fee(platform_id: str, cart_total: float) -> float:
    """Estimate delivery fee from platform defaults + small-order surcharge.
    Returns 0 if the platform isn't recognised (deep-link-only platforms).
    """
    base = DEFAULT_DELIVERY_FEES_INR.get(platform_id, 0.0)
    if cart_total < SMALL_ORDER_FLOOR_INR:
        # Most q-commerce platforms add a ₹15-30 small-order fee
        base += 25.0
    return base


# ---------------------------------------------------------------------------
# Weekly order quota
# ---------------------------------------------------------------------------

async def weekly_quota_remaining(
    family_id: uuid.UUID,
    db: AsyncSession,
    family_max_per_week: int = 3,
) -> int:
    """How many more top-up orders can this family place in the rolling 7d window.
    Counts PLACED + DELIVERED top-up baskets created in the last 7 days.

    Lazy-imports TopupBasket so the rest of this module stays a clean
    pure-function surface that tests can import without touching the DB.
    """
    from app.models.grocery_basket import TopupBasket, TopupBasketStatus

    cutoff = datetime.now(UTC) - timedelta(days=7)
    result = await db.execute(
        select(TopupBasket).where(
            and_(
                TopupBasket.family_id == family_id,
                TopupBasket.status.in_([
                    TopupBasketStatus.PLACED.value,
                    TopupBasketStatus.DELIVERED.value,
                ]),
                TopupBasket.created_at >= cutoff,
            )
        )
    )
    placed_count = len(list(result.scalars().all()))
    return max(0, family_max_per_week - placed_count)


# ---------------------------------------------------------------------------
# Forced batching window
# ---------------------------------------------------------------------------

DEFAULT_PLATFORM_ETA_MIN = 20
DEFAULT_PREP_BUFFER_MIN = 30
DEFAULT_BATCH_WINDOW_HOURS = 4   # how long we'll hold a top-up to absorb more


def latest_safe_order_time(
    meal_datetime: datetime,
    *,
    platform_eta_minutes: int = DEFAULT_PLATFORM_ETA_MIN,
    prep_buffer_minutes: int = DEFAULT_PREP_BUFFER_MIN,
) -> datetime:
    """The latest moment we can fire an order and still be confident the
    cook has the ingredients before they need to start cooking.
    """
    return meal_datetime - timedelta(
        minutes=platform_eta_minutes + prep_buffer_minutes
    )


def batch_window(
    earliest_need: datetime,
    *,
    platform_eta_minutes: int = DEFAULT_PLATFORM_ETA_MIN,
    prep_buffer_minutes: int = DEFAULT_PREP_BUFFER_MIN,
    max_window_hours: int = DEFAULT_BATCH_WINDOW_HOURS,
) -> tuple[datetime, datetime]:
    """Return (open_at, close_at) for a top-up batching window.

    open_at = now (we start collecting immediately)
    close_at = min(latest_safe_order_time, now + max_window_hours)

    The cap is so the window doesn't stretch absurdly when the next meal
    isn't for many hours — we still want to fire the order before the
    user goes to bed wondering where their groceries are.
    """
    now = datetime.now(UTC)
    safe_close = latest_safe_order_time(
        earliest_need,
        platform_eta_minutes=platform_eta_minutes,
        prep_buffer_minutes=prep_buffer_minutes,
    )
    cap = now + timedelta(hours=max_window_hours)
    return now, min(safe_close, cap)


def is_window_ready_to_close(now: datetime, close_at: datetime) -> bool:
    """True when we should stop batching and fire the order."""
    return now >= close_at


# ---------------------------------------------------------------------------
# All-in-one gate
# ---------------------------------------------------------------------------

async def evaluate_topup_order(
    *,
    family_id: uuid.UUID,
    platform_id: str,
    cart_total: float,
    db: AsyncSession,
    family_max_orders_per_week: int = 3,
    family_max_delivery_fee_ratio: float = 0.15,
    delivery_fee: float | None = None,
) -> EconomicsCheck:
    """Run every economic guardrail and return a single approval verdict.

    The caller passes the platform's delivery_fee if known; otherwise we
    estimate from `DEFAULT_DELIVERY_FEES_INR`.
    """
    fee = delivery_fee if delivery_fee is not None else estimate_delivery_fee(platform_id, cart_total)
    ratio = delivery_efficiency(cart_total, fee)
    quota = await weekly_quota_remaining(family_id, db, family_max_orders_per_week)

    if cart_total <= 0:
        return EconomicsCheck(
            approved=False, reason="empty_cart",
            cart_total=cart_total, delivery_fee=fee,
            efficiency_ratio=ratio, quota_remaining=quota,
        )
    if quota <= 0:
        return EconomicsCheck(
            approved=False, reason="weekly_quota_exhausted",
            cart_total=cart_total, delivery_fee=fee,
            efficiency_ratio=ratio, quota_remaining=quota,
        )
    if not is_efficient_enough(ratio, family_max_delivery_fee_ratio):
        return EconomicsCheck(
            approved=False, reason="delivery_fee_too_high",
            cart_total=cart_total, delivery_fee=fee,
            efficiency_ratio=ratio, quota_remaining=quota,
        )

    return EconomicsCheck(
        approved=True, reason="ok",
        cart_total=cart_total, delivery_fee=fee,
        efficiency_ratio=ratio, quota_remaining=quota,
    )
