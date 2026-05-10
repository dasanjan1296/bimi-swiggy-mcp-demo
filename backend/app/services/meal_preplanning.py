"""
Meal pre-planning service — auto-orders missing ingredients before cook arrival.

Flow:
1. Approver plans tomorrow's meal(s) the evening before (or a scheduler suggests them)
2. Engine identifies missing ingredients vs current inventory
3. Cart is created with source "meal_preplan":
   - If auto_order is ON and family auto_approve_threshold covers it → auto-approved
   - Otherwise → sent for approval with a deadline (cook arrival time)
4. If ingredients aren't delivered by cook arrival → fallback meal is activated
   and cook is notified of the updated plan
"""

import json
import logging
import uuid
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cart import Cart, CartStatus
from app.models.inventory import InventoryItem
from app.models.meal_plan import MealPlan, MealPlanStatus
from app.services.meal_engine import suggest_meals

logger = logging.getLogger(__name__)

DEFAULT_COOK_ARRIVAL = time(8, 0)
PREORDER_LEAD_HOURS = 2


async def create_meal_plan(
    family_id: uuid.UUID,
    meal_date: date,
    meal_type: str,
    selected_option: dict,
    fallback_option: dict | None,
    cook_arrival: time | None,
    auto_order: bool,
    db: AsyncSession,
) -> MealPlan:
    """Create a meal plan from a selected suggestion and optional fallback."""
    plan = MealPlan(
        family_id=family_id,
        date=meal_date,
        meal_type=meal_type,
        selected_meal=selected_option.get("name", ""),
        dishes=selected_option.get("dishes", []),
        missing_ingredients_json=json.dumps(selected_option.get("missing_ingredients", [])),
        fallback_meal=fallback_option.get("name") if fallback_option else None,
        fallback_dishes=fallback_option.get("dishes") if fallback_option else None,
        cook_arrival_time=cook_arrival or DEFAULT_COOK_ARRIVAL,
        auto_order=auto_order,
        status=MealPlanStatus.PLANNED,
    )
    db.add(plan)
    await db.flush()

    # Auto-pin the family's default recipe link for this dish (if any).
    # Pure best-effort — if the lookup fails the plan is still valid;
    # the cook just won't get a recipe link in their morning brief.
    try:
        from app.services.recipe_link_service import attach_recipe_to_plan
        await attach_recipe_to_plan(plan=plan, db=db)
    except Exception:  # noqa: BLE001
        logger.exception("recipe_link auto-attach failed for plan %s", plan.id)

    return plan


async def trigger_preplan_orders(db: AsyncSession):
    """
    Scheduled task: find meal plans that need ingredients ordered.
    Called periodically; only acts on plans where the ordering window has opened.
    """
    now = datetime.now(UTC)
    today = date.today()
    tomorrow = today + timedelta(days=1)

    result = await db.execute(
        select(MealPlan).where(
            and_(
                MealPlan.status == MealPlanStatus.PLANNED,
                MealPlan.date.in_([today, tomorrow]),
                MealPlan.missing_ingredients_json.isnot(None),
            )
        )
    )
    plans = list(result.scalars().all())

    for plan in plans:
        missing = json.loads(plan.missing_ingredients_json or "[]")
        if not missing:
            continue

        still_missing = await _check_still_missing(plan.family_id, missing, db)
        if not still_missing:
            logger.info("All ingredients now in stock for plan %s", plan.id)
            plan.status = MealPlanStatus.INGREDIENTS_DELIVERED
            continue

        order_deadline = _get_order_deadline(plan)
        if now < order_deadline - timedelta(hours=PREORDER_LEAD_HOURS):
            continue

        cart = await _create_preplan_cart(plan.family_id, still_missing, plan.auto_order, db)
        plan.cart_id = cart.id
        plan.status = MealPlanStatus.INGREDIENTS_ORDERED

        logger.info(
            "Created preplan cart %s for plan %s (%d items)",
            cart.id, plan.id, len(still_missing),
        )

    await db.commit()


async def check_fallbacks(db: AsyncSession):
    """
    Scheduled task: activate fallback meals when ingredients weren't delivered in time.
    """
    now = datetime.now(UTC)
    today = date.today()

    result = await db.execute(
        select(MealPlan).where(
            and_(
                MealPlan.date == today,
                MealPlan.status == MealPlanStatus.INGREDIENTS_ORDERED,
                MealPlan.cart_id.isnot(None),
            )
        )
    )
    plans = list(result.scalars().all())

    for plan in plans:
        if not plan.cook_arrival_time:
            continue

        cook_arrival_dt = datetime.combine(today, plan.cook_arrival_time, tzinfo=UTC)
        if now < cook_arrival_dt:
            continue

        cart_result = await db.execute(
            select(Cart).where(Cart.id == plan.cart_id)
        )
        cart = cart_result.scalar_one_or_none()

        if cart and cart.status in (CartStatus.DELIVERED, CartStatus.OUT_FOR_DELIVERY):
            plan.status = MealPlanStatus.INGREDIENTS_DELIVERED
            continue

        if plan.fallback_meal and plan.fallback_dishes:
            plan.status = MealPlanStatus.FALLBACK_ACTIVATED
            await _notify_cook_fallback(plan, db)
            logger.info("Fallback activated for plan %s → %s", plan.id, plan.fallback_meal)
        else:
            plan.status = MealPlanStatus.FALLBACK_ACTIVATED
            logger.warning("No fallback defined for plan %s; cook will use available ingredients", plan.id)

    await db.commit()


async def suggest_preplan(
    family_id: uuid.UUID,
    meal_date: date,
    meal_type: str,
    db: AsyncSession,
) -> dict:
    """
    Generate meal suggestions enriched with pre-planning metadata.
    Marks which options need no ordering (all ingredients available)
    and which have fallback potential.
    """
    suggestions = await suggest_meals(family_id, meal_type, db)
    options = suggestions.get("options", [])

    for opt in options:
        missing = opt.get("missing_ingredients", [])
        opt["needs_ordering"] = len(missing) > 0
        opt["ingredient_count"] = len(opt.get("available_ingredients", [])) + len(missing)
        opt["available_ratio"] = (
            len(opt.get("available_ingredients", []))
            / max(opt["ingredient_count"], 1)
        )

    no_order_options = [o for o in options if not o["needs_ordering"]]
    suggestions["fallback_options"] = no_order_options
    suggestions["has_zero_order_option"] = len(no_order_options) > 0

    return suggestions


async def _check_still_missing(
    family_id: uuid.UUID,
    missing: list[dict],
    db: AsyncSession,
) -> list[dict]:
    """Re-check inventory — some items may have been restocked since planning."""
    still_missing = []
    for item in missing:
        name_lower = item["name"].lower().strip()
        result = await db.execute(
            select(InventoryItem).where(
                and_(
                    InventoryItem.family_id == family_id,
                    InventoryItem.item_name.ilike(f"%{name_lower}%"),
                )
            )
        )
        inv = result.scalar_one_or_none()
        needed = item.get("quantity", 0.1)
        if not inv or inv.quantity_remaining < needed:
            still_missing.append(item)
    return still_missing


def _get_order_deadline(plan: MealPlan) -> datetime:
    """Determine the latest time by which ingredients must be ordered."""
    arrival = plan.cook_arrival_time or DEFAULT_COOK_ARRIVAL
    return datetime.combine(plan.date, arrival, tzinfo=UTC)


async def _create_preplan_cart(
    family_id: uuid.UUID,
    missing_items: list[dict],
    auto_order: bool,
    db: AsyncSession,
) -> Cart:
    """Create a grocery cart for pre-planned meal ingredients."""
    from app.services.batching import add_items_to_cart

    items_for_cart = [
        {
            "name": item["name"],
            "quantity": item.get("quantity", 1.0),
            "unit": item.get("unit", "pcs"),
            "urgent": True,
        }
        for item in missing_items
    ]

    cart = await add_items_to_cart(family_id, items_for_cart, db)
    return cart


async def _notify_cook_fallback(plan: MealPlan, db: AsyncSession):
    """Notify the cook that the plan has changed to the fallback meal."""
    from app.models.family import Parent
    from app.services.whatsapp import send_text_message

    result = await db.execute(
        select(Parent).where(
            and_(
                Parent.family_id == plan.family_id,
                Parent.role == "cook",
            )
        )
    )
    cook = result.scalar_one_or_none()
    if not cook:
        return

    fallback_dishes = ", ".join(plan.fallback_dishes or [])
    original_dishes = ", ".join(plan.dishes or [])
    await send_text_message(
        cook.whatsapp_id,
        f"⚠️ Aaj ka plan badal gaya!\n\n"
        f"Pehle: {original_dishes}\n"
        f"Ab banaye: {fallback_dishes}\n\n"
        f"Saamaan samay pe nahi aaya, toh yahi banana hai. 🙏"
    )

    from app.services.notification import notify_family_children
    await notify_family_children(
        family_id=plan.family_id,
        title="Meal plan changed to fallback",
        body=f"Ingredients didn't arrive. Cook will make: {fallback_dishes}",
        data={"type": "meal_fallback", "plan_id": str(plan.id)},
        db=db,
    )
