"""
Kitchen inventory tracker — manages household inventory with EMA-based depletion.

Inventory flows:
- Inflow: restock_from_cart() when a grocery cart is delivered
- Outflow: record_depletion() when a meal is cooked, using estimated consumption
- Estimation: EMA depletion rate learning, same pattern as preference frequency
"""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import InventoryItem

logger = logging.getLogger(__name__)

EMA_ALPHA = 0.3


# SQL LIKE wildcards. Without escaping, a user (or attacker) restocking an
# item literally named "%" or "100%" would fuzzy-match every inventory row
# and accidentally bump unrelated quantities. Postgres uses `\` as the
# default escape char; we explicitly opt-in via `escape="\\"` on the ilike
# call too.
_LIKE_WILDCARDS = ("%", "_", "\\")


def _escape_like(value: str) -> str:
    """Escape SQL LIKE/ILIKE wildcards in a free-text fragment.

    Order matters: `\\` MUST be escaped first, otherwise the subsequent
    escape sequences for `%` and `_` would themselves get re-escaped.
    """
    out = value
    for ch in _LIKE_WILDCARDS:
        out = out.replace(ch, f"\\{ch}")
    return out


async def get_inventory(family_id: uuid.UUID, db: AsyncSession) -> list[InventoryItem]:
    result = await db.execute(
        select(InventoryItem)
        .where(InventoryItem.family_id == family_id)
        .order_by(InventoryItem.category, InventoryItem.item_name)
    )
    return list(result.scalars().all())


async def get_low_stock_items(family_id: uuid.UUID, db: AsyncSession, threshold_days: float = 3.0) -> list[InventoryItem]:
    """Items that will run out within threshold_days based on depletion rate."""
    items = await get_inventory(family_id, db)
    low_stock = []
    for item in items:
        if not item.is_staple:
            continue
        if item.estimated_depletion_rate and item.estimated_depletion_rate > 0:
            days_remaining = item.quantity_remaining / item.estimated_depletion_rate
            if days_remaining <= threshold_days:
                low_stock.append(item)
        elif item.quantity_remaining <= 0:
            low_stock.append(item)
    return low_stock


async def restock_from_cart(family_id: uuid.UUID, cart_items: list[dict], db: AsyncSession) -> list[InventoryItem]:
    """
    Update inventory when a grocery cart is delivered.
    cart_items: list of dicts with keys: name, brand (optional), quantity, unit, category (optional)
    """
    now = datetime.now(UTC)
    updated = []

    for ci in cart_items:
        name_lower = ci["name"].lower().strip()
        if not name_lower:
            continue  # skip empty names entirely
        escaped = _escape_like(name_lower)
        result = await db.execute(
            select(InventoryItem).where(
                and_(
                    InventoryItem.family_id == family_id,
                    InventoryItem.item_name.ilike(
                        f"%{escaped}%", escape="\\",
                    ),
                )
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Loop 9: atomic UPDATE prevents the read-then-write race that
            # under multi-worker load lost concurrent +1 updates.
            #
            # We expire `existing` from the session BEFORE the UPDATE so
            # the ORM doesn't double-flush our increment (once via the
            # explicit UPDATE we issue, once via the dirty-tracked Python
            # attribute change). After UPDATE we refresh from DB.
            qty_delta = ci.get("quantity", 1.0)
            new_brand = ci.get("brand")
            existing_id = existing.id
            db.expire(existing)
            values = {
                "quantity_remaining": InventoryItem.quantity_remaining + qty_delta,
                "last_restocked": now,
            }
            if new_brand:
                values["brand"] = new_brand
            await db.execute(
                update(InventoryItem)
                .where(InventoryItem.id == existing_id)
                .values(**values)
            )
            await db.refresh(existing)
            updated.append(existing)
        else:
            new_item = InventoryItem(
                family_id=family_id,
                item_name=ci["name"],
                brand=ci.get("brand"),
                quantity_remaining=ci.get("quantity", 1.0),
                unit=ci.get("unit", "units"),
                last_restocked=now,
                is_staple=False,
                category=ci.get("category", "other"),
            )
            db.add(new_item)
            updated.append(new_item)

    await db.flush()
    return updated


async def record_depletion(
    family_id: uuid.UUID,
    items_used: list[dict],
    db: AsyncSession,
) -> None:
    """
    Reduce inventory after a meal is cooked.
    items_used: list of dicts with keys: name, quantity_used
    Updates EMA depletion rate.
    """
    for iu in items_used:
        name_lower = iu["name"].lower().strip()
        if not name_lower:
            continue
        escaped = _escape_like(name_lower)
        result = await db.execute(
            select(InventoryItem).where(
                and_(
                    InventoryItem.family_id == family_id,
                    InventoryItem.item_name.ilike(
                        f"%{escaped}%", escape="\\",
                    ),
                )
            )
        )
        item = result.scalar_one_or_none()
        if not item:
            continue

        qty_used = iu.get("quantity_used", 0.0)
        item.quantity_remaining = max(0.0, item.quantity_remaining - qty_used)

        if item.last_restocked:
            days_since = max(
                1.0,
                (datetime.now(UTC) - item.last_restocked).total_seconds() / 86400,
            )
            new_rate = qty_used / days_since
            if item.estimated_depletion_rate:
                item.estimated_depletion_rate = (
                    (1 - EMA_ALPHA) * item.estimated_depletion_rate + EMA_ALPHA * new_rate
                )
            else:
                item.estimated_depletion_rate = new_rate

    await db.flush()


async def upsert_inventory_item(
    family_id: uuid.UUID,
    data: dict,
    db: AsyncSession,
) -> InventoryItem:
    """Create or update an inventory item."""
    item_id = data.get("id")
    if item_id:
        result = await db.execute(
            select(InventoryItem).where(
                and_(InventoryItem.id == item_id, InventoryItem.family_id == family_id)
            )
        )
        item = result.scalar_one_or_none()
        if item:
            for k in ("item_name", "brand", "quantity_remaining", "unit", "is_staple", "category"):
                if k in data and data[k] is not None:
                    setattr(item, k, data[k])
            await db.flush()
            return item

    item = InventoryItem(
        family_id=family_id,
        item_name=data["item_name"],
        brand=data.get("brand"),
        quantity_remaining=data.get("quantity_remaining", 0.0),
        unit=data.get("unit", "units"),
        is_staple=data.get("is_staple", False),
        category=data.get("category", "other"),
    )
    db.add(item)
    await db.flush()
    return item


async def get_inventory_summary(family_id: uuid.UUID, db: AsyncSession) -> str:
    """Build a text summary of current inventory for GPT context."""
    items = await get_inventory(family_id, db)
    if not items:
        return ""

    lines = ["KITCHEN INVENTORY:"]
    by_category: dict[str, list[str]] = {}
    for item in items:
        cat = item.category or "other"
        desc = f"  - {item.item_name}: {item.quantity_remaining:.1f} {item.unit}"
        if item.brand:
            desc += f" ({item.brand})"
        if item.estimated_depletion_rate and item.estimated_depletion_rate > 0:
            days_left = item.quantity_remaining / item.estimated_depletion_rate
            desc += f" [~{days_left:.0f} days left]"
        by_category.setdefault(cat, []).append(desc)

    for cat, descs in sorted(by_category.items()):
        lines.append(f"[{cat.title()}]")
        lines.extend(descs)

    return "\n".join(lines)
