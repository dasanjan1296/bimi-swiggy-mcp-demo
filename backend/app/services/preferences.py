import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import async_session
from app.models.item import PreferenceItem


async def get_preference_context(family_id: uuid.UUID) -> str:
    """Build a text summary of a family's known preferences for the intent prompt."""
    async with async_session() as db:
        result = await db.execute(
            select(PreferenceItem)
            .where(PreferenceItem.family_id == family_id)
            .order_by(PreferenceItem.order_count.desc())
            .limit(30)
        )
        prefs = result.scalars().all()

    if not prefs:
        return ""

    lines = []
    for p in prefs:
        brand_str = f" (brand: {p.brand})" if p.brand else ""
        freq_str = f", ordered every ~{p.frequency_days} days" if p.frequency_days else ""
        lines.append(f"- {p.item_name}{brand_str}: usual qty {p.quantity} {p.unit}{freq_str}")
    return "\n".join(lines)


async def get_family_preferences(
    family_id: uuid.UUID, db: AsyncSession
) -> list[PreferenceItem]:
    result = await db.execute(
        select(PreferenceItem)
        .where(PreferenceItem.family_id == family_id)
        .order_by(PreferenceItem.item_name)
    )
    return list(result.scalars().all())


async def upsert_preference(
    family_id: uuid.UUID,
    item_name: str,
    brand: str | None,
    quantity: float,
    unit: str,
    db: AsyncSession,
) -> PreferenceItem:
    """Create or update a preference item. Auto-learns frequency from order history."""
    result = await db.execute(
        select(PreferenceItem).where(
            PreferenceItem.family_id == family_id,
            PreferenceItem.item_name == item_name,
        )
    )
    pref = result.scalar_one_or_none()

    now = datetime.now(UTC)

    if pref:
        if brand:
            pref.brand = brand
        pref.quantity = quantity
        pref.unit = unit
        pref.order_count += 1

        # Auto-learn frequency
        if pref.last_ordered and pref.order_count >= 2:
            days_since = (now - pref.last_ordered).days
            if days_since > 0:
                if pref.frequency_days:
                    # Exponential moving average
                    pref.frequency_days = int(0.7 * pref.frequency_days + 0.3 * days_since)
                else:
                    pref.frequency_days = days_since

        pref.last_ordered = now
    else:
        pref = PreferenceItem(
            family_id=family_id,
            item_name=item_name,
            brand=brand,
            quantity=quantity,
            unit=unit,
            order_count=1,
            last_ordered=now,
        )
        db.add(pref)

    await db.flush()
    return pref


async def learn_from_cart(family_id: uuid.UUID, items: list[dict], db: AsyncSession):
    """After a cart is approved, update preferences for all items."""
    for item in items:
        await upsert_preference(
            family_id=family_id,
            item_name=item["name"],
            brand=item.get("brand"),
            quantity=item.get("quantity", 1.0),
            unit=item.get("unit", "pcs"),
            db=db,
        )
    await db.commit()


async def get_reorder_suggestions(family_id: uuid.UUID, db: AsyncSession) -> list[PreferenceItem]:
    """Find items that are due for reorder based on frequency prediction."""
    result = await db.execute(
        select(PreferenceItem).where(
            PreferenceItem.family_id == family_id,
            PreferenceItem.frequency_days.isnot(None),
            PreferenceItem.last_ordered.isnot(None),
        )
    )
    prefs = result.scalars().all()

    now = datetime.now(UTC)
    due = []
    for p in prefs:
        days_since = (now - p.last_ordered).days
        if days_since >= (p.frequency_days * 0.85):
            due.append(p)
    return due
