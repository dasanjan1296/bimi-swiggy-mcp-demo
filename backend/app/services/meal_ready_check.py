"""
Cook meal-ready confirmation via WhatsApp.

After the cook's expected finish time, Bimi sends a WhatsApp message asking
whether the meal is ready. The cook's reply is the deterministic signal that
transitions the meal plan to COOKED ("Ready to eat").

Flow:
  1. Scheduler detects plans past expected finish time → sends WhatsApp check
  2. Cook taps "Haan, ban gaya" → status = COOKED, family gets push
  3. Cook taps "Nahi, thodi der" → re-ask in 15 min (max 3 times)
  4. After 3 "no" or 30 min silence → notify family that meal is delayed
"""

import logging
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.family import Parent
from app.models.meal_plan import MealPlan, MealPlanStatus

logger = logging.getLogger(__name__)

MAX_READY_CHECKS = 3
RECHECK_MINUTES = 15
DEFAULT_COOK_TIME_MINUTES = 45


async def send_meal_ready_check(plan: MealPlan, db: AsyncSession) -> bool:
    """
    Send a WhatsApp message to the cook asking if the meal is ready.
    Returns True if the message was sent, False if no cook found.
    """
    from app.services.comm_adapter import get_or_create_profile
    from app.services.whatsapp import send_reply_buttons

    cook = await _get_family_cook(plan.family_id, db)
    if not cook or not cook.whatsapp_id:
        return False

    profile = await get_or_create_profile(plan.family_id, "parent", cook.id, db)
    meal_label = plan.meal_type.title()
    dishes = ", ".join(plan.dishes) if plan.dishes else plan.selected_meal

    if profile and profile.is_english_dominant:
        body = f"Is {meal_label.lower()} ready?\n\n{dishes}"
        btn_yes = "Yes, it's ready"
        btn_no = "Not yet, 15 min"
    else:
        body = f"Kya {meal_label.lower()} ban gaya?\n\n{dishes}"
        btn_yes = "Haan, ban gaya"
        btn_no = "Nahi, thodi der"

    await send_reply_buttons(
        to=cook.whatsapp_id,
        body=body,
        buttons=[
            {"id": f"meal_ready_yes_{plan.id}", "title": btn_yes},
            {"id": f"meal_ready_no_{plan.id}", "title": btn_no},
        ],
        footer="Bimi",
    )

    plan.ready_check_count = (plan.ready_check_count or 0) + 1
    logger.info(
        "Sent meal-ready check #%d for plan %s (%s %s)",
        plan.ready_check_count, plan.id, plan.date, plan.meal_type,
    )
    return True


async def handle_meal_ready_response(
    plan_id: uuid.UUID, is_ready: bool, cook_wa_id: str, db: AsyncSession
):
    """Handle the cook's button reply to a meal-ready check."""
    from app.services.comm_adapter import get_or_create_profile
    from app.services.notification import notify_family_children
    from app.services.whatsapp import send_text_message

    plan = await db.get(MealPlan, plan_id)
    if not plan:
        logger.warning("meal_ready response for unknown plan %s", plan_id)
        return

    if plan.status == MealPlanStatus.COOKED:
        return

    cook = await _get_cook_by_wa_id(cook_wa_id, db)
    profile = None
    if cook:
        profile = await get_or_create_profile(plan.family_id, "parent", cook.id, db)

    is_english = profile and profile.is_english_dominant
    meal_label = plan.meal_type.title()
    dishes = ", ".join(plan.dishes) if plan.dishes else plan.selected_meal

    if is_ready:
        plan.status = MealPlanStatus.COOKED
        await db.flush()

        if is_english:
            await send_text_message(cook_wa_id, "Great! Told the family that the meal is ready. 👍")
        else:
            await send_text_message(cook_wa_id, "Bahut badhiya! Sahab/Ma'am ko bata diya. 👍")

        await notify_family_children(
            family_id=plan.family_id,
            title=f"{meal_label} is ready!",
            body=f"{dishes} — ready to eat.",
            data={"type": "meal_ready", "plan_id": str(plan.id), "meal_type": plan.meal_type},
            db=db,
        )
        logger.info("Plan %s marked COOKED via cook confirmation", plan.id)

    else:
        checks = plan.ready_check_count or 0
        if checks >= MAX_READY_CHECKS:
            if is_english:
                await send_text_message(cook_wa_id, "Okay, let the family know when it's done. 🙏")
            else:
                await send_text_message(cook_wa_id, "Theek hai, jab ban jaye toh bata dena. 🙏")

            await notify_family_children(
                family_id=plan.family_id,
                title=f"{meal_label} is delayed",
                body=f"{dishes} is taking longer than expected. Cook has been notified.",
                data={"type": "meal_delayed", "plan_id": str(plan.id), "meal_type": plan.meal_type},
                db=db,
            )
            logger.info("Plan %s: max checks reached, notified family of delay", plan.id)
        else:
            if is_english:
                await send_text_message(cook_wa_id, "Okay, I'll check again in 15 minutes. 🙏")
            else:
                await send_text_message(cook_wa_id, "Theek hai, 15 minute baad phir poochungi. 🙏")


async def transition_to_cooking(db: AsyncSession):
    """
    Transition plans to COOKING status when the cook's arrival time has passed.
    Called periodically by the scheduler.
    """
    now_utc = datetime.now(UTC)
    today = date.today()

    cookable_statuses = [
        MealPlanStatus.PLANNED,
        MealPlanStatus.INGREDIENTS_DELIVERED,
        MealPlanStatus.FALLBACK_ACTIVATED,
    ]

    result = await db.execute(
        select(MealPlan).where(
            and_(
                MealPlan.date == today,
                MealPlan.status.in_([s.value for s in cookable_statuses]),
                MealPlan.cook_arrival_time.isnot(None),
            )
        )
    )
    plans = list(result.scalars().all())

    for plan in plans:
        arrival_dt = datetime.combine(today, plan.cook_arrival_time, tzinfo=UTC)
        if now_utc >= arrival_dt:
            plan.status = MealPlanStatus.COOKING
            logger.info("Plan %s transitioned to COOKING (cook arrived)", plan.id)

    if plans:
        await db.commit()


async def check_and_send_ready_prompts(db: AsyncSession):
    """
    Find COOKING plans past their expected finish time and send ready checks.
    Called periodically by the scheduler.
    """
    now_utc = datetime.now(UTC)
    today = date.today()

    result = await db.execute(
        select(MealPlan).where(
            and_(
                MealPlan.date == today,
                MealPlan.status == MealPlanStatus.COOKING,
                MealPlan.cook_arrival_time.isnot(None),
            )
        )
    )
    plans = list(result.scalars().all())

    for plan in plans:
        checks = plan.ready_check_count or 0
        if checks >= MAX_READY_CHECKS:
            continue

        expected_done = datetime.combine(
            today, plan.cook_arrival_time, tzinfo=UTC
        ) + timedelta(minutes=DEFAULT_COOK_TIME_MINUTES)

        next_check_time = expected_done + timedelta(minutes=RECHECK_MINUTES * checks)

        if now_utc < next_check_time:
            continue

        sent = await send_meal_ready_check(plan, db)
        if not sent:
            logger.info("No cook found for plan %s, skipping ready check", plan.id)

    await db.commit()


async def check_stale_cooking_plans(db: AsyncSession):
    """
    Notify the family if a COOKING plan has had no response for 30+ minutes
    past expected done time and max checks were sent.
    """
    from app.services.notification import notify_family_children

    now_utc = datetime.now(UTC)
    today = date.today()

    result = await db.execute(
        select(MealPlan).where(
            and_(
                MealPlan.date == today,
                MealPlan.status == MealPlanStatus.COOKING,
                MealPlan.ready_check_count >= MAX_READY_CHECKS,
                MealPlan.cook_arrival_time.isnot(None),
            )
        )
    )
    plans = list(result.scalars().all())

    for plan in plans:
        expected_done = datetime.combine(
            today, plan.cook_arrival_time, tzinfo=UTC
        ) + timedelta(minutes=DEFAULT_COOK_TIME_MINUTES)
        stale_threshold = expected_done + timedelta(
            minutes=RECHECK_MINUTES * MAX_READY_CHECKS + 15
        )

        if now_utc >= stale_threshold:
            meal_label = plan.meal_type.title()
            dishes = ", ".join(plan.dishes) if plan.dishes else plan.selected_meal
            await notify_family_children(
                family_id=plan.family_id,
                title=f"{meal_label} — no update from cook",
                body=f"Cook hasn't confirmed if {dishes} is ready. You may want to check with them.",
                data={"type": "meal_stale", "plan_id": str(plan.id)},
                db=db,
            )
            plan.ready_check_count = MAX_READY_CHECKS + 1
            logger.info("Stale notification sent for plan %s", plan.id)

    if plans:
        await db.commit()


async def _get_family_cook(family_id: uuid.UUID, db: AsyncSession) -> Parent | None:
    result = await db.execute(
        select(Parent).where(
            and_(Parent.family_id == family_id, Parent.role == "cook")
        )
    )
    return result.scalar_one_or_none()


async def _get_cook_by_wa_id(wa_id: str, db: AsyncSession) -> Parent | None:
    result = await db.execute(
        select(Parent).where(Parent.whatsapp_id == wa_id)
    )
    return result.scalar_one_or_none()
