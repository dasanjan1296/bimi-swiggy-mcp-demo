"""
Weekly bulk basket lifecycle:

  - On the family's `weekly_bulk_day`, sweep open WeeklyBasket rows.
  - For each basket whose estimated_total >= weekly_bulk_min_total, route
    to Swiggy Instamart (the only grocery platform after the multi-platform
    retirement), build a multi-item deep link, and notify the family.
  - The family checks out themselves via the deep link. We mark sent_at
    immediately and rely on a follow-up "I placed it" tap to mark COMPLETED.

The deep-link hand-off is preserved for now; Loop 5 will replace it with
the real Swiggy MCP order placement once Builders Club access is approved.
"""

from __future__ import annotations

import logging
import urllib.parse
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.family import Family
from app.models.grocery_basket import WeeklyBasket, WeeklyBasketStatus
from app.services.platforms import GROCERY_PLATFORM_IDS, get_platform

# Weekly bulk basket now ships exclusively via Swiggy Instamart (formerly
# routed across BigBasket / DMart / JioMart / Flipkart Minutes / Amazon Fresh
# before the multi-platform retirement).
BULK_PLATFORM_IDS = GROCERY_PLATFORM_IDS

logger = logging.getLogger(__name__)


async def send_due_weekly_baskets(db: AsyncSession) -> int:
    """Find COLLECTING weekly baskets where today is the family's bulk day
    AND the basket meets the family's minimum total. Send a deep-link
    notification for each. Returns the number of baskets sent.
    """
    today = date.today()
    today_name = today.strftime("%A").lower()

    result = await db.execute(
        select(WeeklyBasket, Family)
        .join(Family, WeeklyBasket.family_id == Family.id)
        .where(WeeklyBasket.status == WeeklyBasketStatus.COLLECTING.value)
    )
    rows = result.all()
    sent = 0

    for basket, family in rows:
        if family.weekly_bulk_day.lower() != today_name:
            continue
        if basket.estimated_total < family.weekly_bulk_min_total:
            logger.info(
                "Weekly basket %s skipped — under min total (%.0f < %.0f)",
                basket.id, basket.estimated_total, family.weekly_bulk_min_total,
            )
            continue

        platform_id, deep_link = _pick_bulk_platform(basket.items)
        if not platform_id or not deep_link:
            logger.warning("Weekly basket %s: no bulk platform deep-link buildable", basket.id)
            continue

        basket.platform_id = platform_id
        basket.deep_link_url = deep_link
        basket.status = WeeklyBasketStatus.SENT_TO_USER.value
        basket.sent_at = datetime.now(UTC)

        await _notify_weekly_basket_ready(family, basket, db)
        sent += 1

    if sent:
        await db.commit()
    return sent


async def mark_weekly_basket_completed(
    basket_id,
    db: AsyncSession,
) -> WeeklyBasket | None:
    """User tapped 'I placed the order'. Mark the basket completed so a
    fresh COLLECTING basket is opened for next week's accumulation.
    """
    basket = await db.get(WeeklyBasket, basket_id)
    if not basket:
        return None
    basket.status = WeeklyBasketStatus.COMPLETED.value
    basket.completed_at = datetime.now(UTC)
    await db.flush()
    return basket


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _pick_bulk_platform(items: list[dict]) -> tuple[str | None, str | None]:
    """Build a Swiggy Instamart deep link for the basket items.

    Multi-platform routing was retired with the move to Swiggy-only
    commerce. This function now always returns the Swiggy Instamart pair
    (or `(None, None)` when there's nothing to send).
    """
    if not items:
        return None, None

    pid = "swiggy_instamart"
    platform = get_platform(pid)
    if not platform or not platform.deep_link_template:
        return None, None

    query = ", ".join(it.get("name", "") for it in items[:10] if it.get("name"))
    if not query:
        return None, None
    url = platform.deep_link_template.format(query=urllib.parse.quote(query))
    return pid, url


async def _notify_weekly_basket_ready(
    family: Family,
    basket: WeeklyBasket,
    db: AsyncSession,
) -> None:
    item_count = len(basket.items)
    platform = get_platform(basket.platform_id) if basket.platform_id else None
    platform_label = platform.name if platform else "your bulk grocer"

    title = f"Weekly groceries ready — {item_count} items"
    body = (
        f"~₹{basket.estimated_total:.0f} on {platform_label}. "
        f"Tap to review and check out. Bimi batched these so you save on delivery."
    )

    data = {
        "type": "weekly_basket_ready",
        "basket_id": str(basket.id),
        "platform_id": basket.platform_id or "",
        "deep_link": basket.deep_link_url or "",
        "estimated_total": str(basket.estimated_total),
        "item_count": str(item_count),
    }

    try:
        from app.services.notification import notify_family_children
        await notify_family_children(
            family_id=family.id,
            title=title,
            body=body,
            data=data,
            db=db,
        )
    except Exception:
        logger.exception("Failed to push weekly basket notification")
