import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_db
from app.models.cart import Cart, CartStatus
from app.models.family import Child, Parent
from app.schemas.cart import CartApproveRequest, CartEditRequest, CartOut, DeliveryStatusUpdate
from app.services.auth import get_current_child, require_entity_access, require_family_access
from app.services.notification import notify_cart_handled
from app.services.platforms import get_deeplink_url
from app.services.preferences import learn_from_cart
from app.services.whatsapp import (
    send_arriving_soon,
    send_delivered,
    send_delivery_scheduled,
    send_order_placed,
    send_out_for_delivery,
)

router = APIRouter(prefix="/carts", tags=["carts"])
logger = logging.getLogger(__name__)


@router.get("/", response_model=list[CartOut])
async def list_carts(
    family_id: uuid.UUID,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_child: Child = Depends(get_current_child),
):
    require_family_access(current_child, family_id)
    query = (
        select(Cart)
        .where(Cart.family_id == family_id)
        .options(selectinload(Cart.items))
        .order_by(Cart.created_at.desc())
        .limit(20)
    )
    if status:
        query = query.where(Cart.status == status)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{cart_id}", response_model=CartOut)
async def get_cart(cart_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_child: Child = Depends(get_current_child)):
    result = await db.execute(
        select(Cart).where(Cart.id == cart_id).options(selectinload(Cart.items))
    )
    cart = result.scalar_one_or_none()
    if not cart:
        raise HTTPException(404, "Cart not found")
    require_entity_access(current_child, cart)
    return cart


@router.post("/{cart_id}/approve", response_model=CartOut)
async def approve_cart(
    cart_id: uuid.UUID,
    body: CartApproveRequest,
    db: AsyncSession = Depends(get_db),
    current_child: Child = Depends(get_current_child),
):
    result = await db.execute(
        select(Cart).where(Cart.id == cart_id).options(selectinload(Cart.items))
    )
    cart = result.scalar_one_or_none()
    if not cart:
        raise HTTPException(404, "Cart not found")
    require_entity_access(current_child, cart)
    if cart.status != CartStatus.PENDING_APPROVAL:
        raise HTTPException(400, f"Cart is already {cart.status.value}")

    # Mark approved
    cart.status = CartStatus.APPROVED
    cart.approved_by = body.child_id
    cart.approved_at = datetime.now(UTC)

    # Learn preferences from this order (legacy + HCG)
    items_dicts = [
        {"name": item.name, "brand": item.brand, "quantity": item.quantity, "unit": item.unit}
        for item in cart.items
    ]
    await learn_from_cart(cart.family_id, items_dicts, db)

    # HCG Bayesian learning from cart approval
    try:
        from app.services.bayesian_engine import learn_from_cart_approval
        requester_id = cart.requester_id if hasattr(cart, "requester_id") else None
        if requester_id:
            await learn_from_cart_approval(cart.family_id, requester_id, items_dicts, db)
    except Exception:  # noqa: BLE001 — best-effort HCG learning
        logger.exception("HCG learn_from_cart_approval failed for cart %s", cart.id)

    # Attempt Swiggy MCP auto-ordering. Pre-Loop-5 the dispatcher returns
    # success=False; the cart stays in APPROVED state for manual handoff.
    from app.services.mcp_ordering import OrderMethod, dispatcher

    if cart.best_platform:
        items_payload = [
            {
                "name": it.name,
                "brand": it.brand,
                "quantity": it.quantity,
                "unit": it.unit,
            }
            for it in cart.items
        ]
        order_result = await dispatcher.place_order(cart.best_platform, items_payload)
        if order_result.success and order_result.method == OrderMethod.MCP:
            cart.status = CartStatus.ORDERED
            cart.ordered_at = datetime.now(UTC)
            cart.delivery_platform = order_result.platform_name
            cart.tracking_link = order_result.tracking_link
            cart.delivery_eta = order_result.delivery_eta
        elif order_result.deep_link:
            cart.deep_link = order_result.deep_link

    await db.commit()
    await db.refresh(cart, ["items"])

    # Notify siblings that this was handled
    child_result = await db.execute(select(Child).where(Child.id == body.child_id))
    child = child_result.scalar_one_or_none()
    handler_name = child.name if child else "someone"
    await notify_cart_handled(cart, handler_name)

    # Confirm to parent via WhatsApp with delivery details
    parent_result = await db.execute(
        select(Parent).where(Parent.family_id == cart.family_id).limit(1)
    )
    parent = parent_result.scalar_one_or_none()
    if parent:
        platform_name = cart.delivery_platform or cart.best_platform or "the store"
        try:
            await send_order_placed(
                to=parent.whatsapp_id,
                item_count=cart.item_count,
                platform=platform_name,
                delivery_eta=cart.delivery_eta,
                delivery_slot=cart.delivery_slot,
                tracking_link=cart.tracking_link,
            )
        except Exception:  # noqa: BLE001 — best-effort delivery notification
            logger.exception(
                "send_order_placed failed for cart %s (parent unreachable)", cart.id,
            )

    return cart


@router.post("/{cart_id}/edit", response_model=CartOut)
async def edit_cart(
    cart_id: uuid.UUID,
    body: CartEditRequest,
    db: AsyncSession = Depends(get_db),
    current_child: Child = Depends(get_current_child),
):
    result = await db.execute(
        select(Cart).where(Cart.id == cart_id).options(selectinload(Cart.items))
    )
    cart = result.scalar_one_or_none()
    if not cart:
        raise HTTPException(404, "Cart not found")
    require_entity_access(current_child, cart)
    if cart.status != CartStatus.PENDING_APPROVAL:
        raise HTTPException(400, "Cart cannot be edited in current state")

    items_by_id = {item.id: item for item in cart.items}

    for edit in body.edits:
        item = items_by_id.get(edit.item_id)
        if not item:
            continue
        if edit.remove:
            await db.delete(item)
            cart.item_count = max(0, (cart.item_count or 1) - 1)
        else:
            if edit.quantity is not None:
                item.quantity = edit.quantity
            if edit.brand is not None:
                item.brand = edit.brand

    # Recalculate total
    await db.flush()
    await db.refresh(cart, ["items"])
    total = sum((it.best_price or 0) * it.quantity for it in cart.items)
    cart.estimated_total = total

    if cart.best_platform:
        item_query = ", ".join(it.name for it in cart.items[:5])
        cart.deep_link = get_deeplink_url(cart.best_platform, item_query)

    await db.commit()
    await db.refresh(cart, ["items"])
    return cart


@router.post("/{cart_id}/skip", response_model=CartOut)
async def skip_cart(cart_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_child: Child = Depends(get_current_child)):
    result = await db.execute(
        select(Cart).where(Cart.id == cart_id).options(selectinload(Cart.items))
    )
    cart = result.scalar_one_or_none()
    if not cart:
        raise HTTPException(404, "Cart not found")
    require_entity_access(current_child, cart)
    cart.status = CartStatus.SKIPPED
    await db.commit()
    await db.refresh(cart, ["items"])
    return cart


@router.post("/{cart_id}/mark-ordered", response_model=CartOut)
async def mark_ordered(
    cart_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_child: Child = Depends(get_current_child),
):
    """
    Approver calls this after completing purchase on the platform via deep link.
    Sets cart to ORDERED and notifies the requester.
    """
    result = await db.execute(
        select(Cart).where(Cart.id == cart_id).options(selectinload(Cart.items))
    )
    cart = result.scalar_one_or_none()
    if not cart:
        raise HTTPException(404, "Cart not found")
    require_entity_access(current_child, cart)

    if cart.status not in (CartStatus.APPROVED, CartStatus.PENDING_APPROVAL):
        raise HTTPException(400, f"Cart cannot be marked ordered in {cart.status.value} state")

    if cart.status == CartStatus.PENDING_APPROVAL:
        cart.approved_by = current_child.id
        cart.approved_at = datetime.now(UTC)

    cart.status = CartStatus.ORDERED
    cart.ordered_at = datetime.now(UTC)
    cart.delivery_platform = cart.best_platform

    await db.commit()
    await db.refresh(cart, ["items"])

    parent_result = await db.execute(
        select(Parent).where(Parent.family_id == cart.family_id).limit(1)
    )
    parent = parent_result.scalar_one_or_none()
    if parent:
        platform_name = cart.delivery_platform or "the store"
        try:
            await send_order_placed(
                to=parent.whatsapp_id,
                item_count=cart.item_count,
                platform=platform_name,
                delivery_eta=None,
                delivery_slot=None,
                tracking_link=None,
            )
        except Exception:  # noqa: BLE001 — best-effort delivery notification
            logger.exception(
                "send_order_placed (manual fallback) failed for cart %s", cart.id,
            )

    return cart


@router.post("/{cart_id}/delivery-update", response_model=CartOut)
async def update_delivery_status(
    cart_id: uuid.UUID,
    body: DeliveryStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_child: Child = Depends(get_current_child),
):
    """
    Child updates delivery status after placing order on the platform.
    Triggers WhatsApp messages to Mom at each stage.
    """
    result = await db.execute(
        select(Cart).where(Cart.id == cart_id).options(selectinload(Cart.items))
    )
    cart = result.scalar_one_or_none()
    if not cart:
        raise HTTPException(404, "Cart not found")
    require_entity_access(current_child, cart)

    if body.delivery_platform:
        cart.delivery_platform = body.delivery_platform
    if body.delivery_eta:
        cart.delivery_eta = body.delivery_eta
    if body.delivery_slot:
        cart.delivery_slot = body.delivery_slot
    if body.tracking_link:
        cart.tracking_link = body.tracking_link

    parent_result = await db.execute(
        select(Parent).where(Parent.family_id == cart.family_id).limit(1)
    )
    parent = parent_result.scalar_one_or_none()

    if body.status == "ordered":
        cart.status = CartStatus.ORDERED
        cart.ordered_at = datetime.now(UTC)
        if parent:
            if body.delivery_slot:
                await send_delivery_scheduled(
                    parent.whatsapp_id, cart.item_count, cart.delivery_platform or "Store",
                    body.delivery_slot,
                )
            else:
                await send_order_placed(
                    parent.whatsapp_id, cart.item_count, cart.delivery_platform or "Store",
                    body.delivery_eta, body.delivery_slot, body.tracking_link,
                )

    elif body.status == "out_for_delivery":
        cart.status = CartStatus.OUT_FOR_DELIVERY
        if parent:
            eta_min = None
            if body.delivery_eta and body.delivery_eta.isdigit():
                eta_min = int(body.delivery_eta)
            await send_out_for_delivery(parent.whatsapp_id, eta_min, body.tracking_link)

    elif body.status == "arriving_soon":
        if parent:
            await send_arriving_soon(parent.whatsapp_id)

    elif body.status == "delivered":
        cart.status = CartStatus.DELIVERED
        cart.delivered_at = datetime.now(UTC)
        if parent:
            await send_delivered(parent.whatsapp_id, cart.item_count)

    await db.commit()
    await db.refresh(cart, ["items"])
    return cart
