import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.cart import Cart, CartItem, CartStatus

logger = logging.getLogger(__name__)

PERISHABLES = {"milk", "doodh", "eggs", "anda", "bread", "curd", "dahi", "paneer", "fruits", "vegetables", "sabzi"}


async def add_items_to_cart(
    family_id: uuid.UUID, items: list[dict], db: AsyncSession
) -> Cart:
    """
    Add extracted items to the family's running cart.
    Creates a new cart if none is accumulating.
    Triggers the cart immediately if any item is urgent or perishable.
    """
    # Find or create the accumulating cart
    result = await db.execute(
        select(Cart).where(
            Cart.family_id == family_id,
            Cart.status == CartStatus.ACCUMULATING,
        )
    )
    cart = result.scalar_one_or_none()

    if not cart:
        cart = Cart(family_id=family_id, status=CartStatus.ACCUMULATING)
        db.add(cart)
        await db.flush()

    has_urgent = False
    for item in items:
        is_perishable = item["name"].lower().strip() in PERISHABLES
        urgent = item.get("urgent", False) or is_perishable
        if urgent:
            has_urgent = True

        cart_item = CartItem(
            cart_id=cart.id,
            name=item["name"],
            brand=item.get("brand"),
            quantity=item.get("quantity", 1.0),
            unit=item.get("unit", "pcs"),
            urgent=urgent,
        )
        db.add(cart_item)

    cart.item_count = (cart.item_count or 0) + len(items)
    await db.commit()
    await db.refresh(cart)

    # Check trigger conditions
    should_trigger = _should_trigger(cart, has_urgent)
    if should_trigger:
        await trigger_cart(cart, db)

    return cart


def _should_trigger(cart: Cart, has_urgent: bool) -> bool:
    """Evaluate whether a cart should move to pending_approval."""
    if has_urgent:
        return True

    # Estimate total (rough Rs 150 per item heuristic until price comparison runs)
    estimated = (cart.item_count or 0) * 150
    if estimated >= settings.batch_min_amount:
        return True

    # Time-based: 24h since cart creation
    if cart.created_at:
        age = datetime.now(UTC) - cart.created_at.replace(tzinfo=UTC)
        if age >= timedelta(hours=settings.batch_max_wait_hours):
            return True

    return False


async def trigger_cart(cart: Cart, db: AsyncSession):
    """
    Move a cart from accumulating -> pending_approval.

    With the multi-platform retirement, every cart routes to Swiggy Instamart.
    Loop 5 will reintroduce real-time price/availability lookups via the Swiggy
    MCP adapter; until then we set the platform fields to Swiggy and rely on
    the existing item-level estimated_unit_price totals on cart.items.
    """
    from app.services.notification import notify_children
    from app.services.platforms import get_deeplink_url, get_platform

    cart.status = CartStatus.PENDING_APPROVAL
    cart.triggered_at = datetime.now(UTC)

    cart.best_platform = "swiggy_instamart"
    await db.refresh(cart, ["items"])
    # Loop 14: Decimal aggregation. Loop 12 moved storage to Numeric(10,2)
    # for decimal-exact storage + SQL comparisons. But Python `sum(... *
    # ...)` is still float arithmetic — cart-of-30-items can drift ~1e-10
    # per cart, and cross-month aggregations compound that drift into
    # visible accountant errors. Coerce to Decimal here and convert
    # back to float at the boundary (the column is asdecimal=False so
    # SQLAlchemy expects float on write).
    from decimal import Decimal

    decimal_total = sum(
        (Decimal(str(item.quantity or 0)) * Decimal(str(item.best_price or 0)))
        for item in cart.items
    )
    cart.estimated_total = float(decimal_total)

    item_names = ", ".join(item.name for item in cart.items[:5])
    cart.deep_link = get_deeplink_url("swiggy_instamart", item_names)
    platform = get_platform("swiggy_instamart")
    if platform:
        cart.delivery_platform = f"{platform.name} (auto-order available)"

    await db.commit()

    # Check if this family has auto-approve enabled
    from app.models.family import Family
    fam_result = await db.execute(select(Family).where(Family.id == cart.family_id))
    family = fam_result.scalar_one_or_none()

    if family and family.self_use:
        # Self-use mode: auto-approve everything, notify via WhatsApp only
        await _auto_approve_cart(cart, family, db)
    elif family and family.auto_approve_threshold and cart.estimated_total <= family.auto_approve_threshold:
        # Under budget threshold: auto-approve, notify children silently
        await _auto_approve_cart(cart, family, db)
        await notify_children(cart)  # silent notification for visibility
    else:
        # Standard flow: notify children for manual approval
        await notify_children(cart)


async def _auto_approve_cart(cart: Cart, family, db: AsyncSession):
    """
    Auto-approve a cart without child intervention.
    Used for self-use mode and under-threshold auto-approve.
    Attempts MCP ordering, sends WhatsApp confirmation to requester.
    """
    from app.models.family import Parent
    from app.services.mcp_ordering import OrderMethod, dispatcher
    from app.services.preferences import learn_from_cart
    from app.services.whatsapp import send_order_placed

    cart.status = CartStatus.APPROVED
    cart.approved_at = datetime.now(UTC)

    items_dicts = [
        {"name": item.name, "brand": item.brand, "quantity": item.quantity, "unit": item.unit}
        for item in cart.items
    ]
    await learn_from_cart(cart.family_id, items_dicts, db)

    # Attempt Swiggy MCP auto-ordering. Pre-Loop-5 the dispatcher returns
    # success=False with a clear error; we fall through to manual approval.
    if cart.best_platform:
        order_result = await dispatcher.place_order(
            cart.best_platform, items_dicts,
        )
        if order_result.success and order_result.method == OrderMethod.MCP:
            cart.status = CartStatus.ORDERED
            cart.ordered_at = datetime.now(UTC)
            cart.delivery_platform = order_result.platform_name
            cart.tracking_link = order_result.tracking_link
            cart.delivery_eta = order_result.delivery_eta

    await db.commit()

    # Notify requester via WhatsApp
    parent_result = await db.execute(
        select(Parent).where(Parent.family_id == cart.family_id).limit(1)
    )
    parent = parent_result.scalar_one_or_none()
    if parent:
        auto_label = "Auto-approved" if not family.self_use else "Order placed"
        try:
            await send_order_placed(
                to=parent.whatsapp_id,
                item_count=cart.item_count,
                platform=cart.delivery_platform or cart.best_platform or "best platform",
                delivery_eta=cart.delivery_eta,
                delivery_slot=cart.delivery_slot,
                tracking_link=cart.tracking_link,
            )
        except Exception:  # noqa: BLE001 — best-effort delivery push
            logger.exception(
                "send_order_placed (batch path) failed for cart %s", cart.id,
            )


async def trigger_cart_for_family(family_id: uuid.UUID, db: AsyncSession):
    """Manually trigger the accumulating cart for a family (e.g., parent says 'send to beta')."""
    result = await db.execute(
        select(Cart).where(
            Cart.family_id == family_id,
            Cart.status == CartStatus.ACCUMULATING,
        )
    )
    cart = result.scalar_one_or_none()
    if cart and cart.item_count and cart.item_count > 0:
        await trigger_cart(cart, db)


async def clear_accumulating_cart(family_id: uuid.UUID, db: AsyncSession):
    """Delete the accumulating cart for a family (parent says 'clear cart')."""
    result = await db.execute(
        select(Cart).where(
            Cart.family_id == family_id,
            Cart.status == CartStatus.ACCUMULATING,
        )
    )
    cart = result.scalar_one_or_none()
    if cart:
        await db.delete(cart)
        await db.commit()


async def check_stale_carts():
    """
    Periodic job: find accumulating carts that have exceeded time thresholds
    and trigger them for approval.
    """
    from app.db import async_session

    async with async_session() as db:
        now = datetime.now(UTC)
        cutoff_soft = now - timedelta(hours=settings.batch_max_wait_hours)
        cutoff_hard = now - timedelta(days=settings.batch_hard_max_days)

        result = await db.execute(
            select(Cart).where(
                Cart.status == CartStatus.ACCUMULATING,
                Cart.created_at <= cutoff_soft,
            )
        )
        stale_carts = result.scalars().all()

        for cart in stale_carts:
            logger.info("Triggering stale cart %s (family %s)", cart.id, cart.family_id)
            await trigger_cart(cart, db)

        # Expire carts pending approval for > 3 days with no response
        result = await db.execute(
            select(Cart).where(
                Cart.status == CartStatus.PENDING_APPROVAL,
                Cart.triggered_at <= cutoff_hard,
            )
        )
        expired_carts = result.scalars().all()
        for cart in expired_carts:
            cart.status = CartStatus.EXPIRED
            logger.info("Expiring cart %s", cart.id)

        await db.commit()
