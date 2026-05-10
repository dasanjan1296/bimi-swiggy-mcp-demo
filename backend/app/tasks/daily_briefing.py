"""
Daily Briefing System — Scheduled messages for cooks and users.

Jobs:
- 7:00 AM IST: Cook morning briefing (meals + tasks + deliveries)
- 7:00 AM IST: User meal expectations for the day
- 8:00 PM IST: User evening preview (tomorrow's breakfast plan)
- 9:00 PM IST: User end-of-day summary
- Sunday 10:00 AM IST: Weekly digest
"""
import asyncio
import logging
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from app.db import async_session
from app.models.family import Family, Parent
from app.models.meal import MealLog
from app.models.standing_instruction import StandingInstruction

logger = logging.getLogger(__name__)

IST_OFFSET = timedelta(hours=5, minutes=30)


def _run_async(coro):
    """Bridge sync APScheduler callback to async coroutine."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(coro)
        else:
            loop.run_until_complete(coro)
    except RuntimeError:
        asyncio.run(coro)


# ---------------------------------------------------------------------------
# Scheduled job entry points (sync, for APScheduler)
# ---------------------------------------------------------------------------

def send_morning_briefings():
    """7 AM IST — Send morning briefing to all cooks."""
    _run_async(_send_all_morning_briefings())


def send_user_meal_expectations():
    """7 AM IST — Send meal expectations to all users."""
    _run_async(_send_all_meal_expectations())


def send_evening_preview():
    """8 PM IST — Send tomorrow's breakfast preview to users."""
    _run_async(_send_all_evening_previews())


def send_eod_summary():
    """9 PM IST — Send end-of-day summary to users."""
    _run_async(_send_all_eod_summaries())


def send_weekly_digest():
    """Sunday 10 AM IST — Send weekly digest to users."""
    _run_async(_send_all_weekly_digests())


def check_meal_ready_status():
    """Every 10 min — Transition plans to COOKING at cook arrival, then prompt cook for ready confirmation."""
    _run_async(_check_meal_ready_status())


def send_attendance_checkins():
    """6:30 AM IST — Send the morning attendance check-in card to each cook."""
    _run_async(_send_all_attendance_checkins())


def send_sunday_stock_check():
    """Sunday 10 AM IST — Voice prompt to each cook for stock status."""
    _run_async(_send_all_sunday_stock_checks())


_SUNDAY_STOCK_VOICE = (
    "Namaste! Aaj Sunday hai — kitchen mein kya khatam hai? "
    "Voice note mein bata dijiye, hum cart bana ke ghar walon ko bhej denge."
)
_SUNDAY_STOCK_TEXT = (
    "🛒 Sunday Stock Check\n\n"
    "Kya khatam hai? Voice note ya text bhej dijiye:\n"
    "- Atta, doodh, sabzi — jo bhi yaad ho.\n"
    "- Hum cart bana denge, ghar walon ko approve karna hoga."
)


async def send_sunday_stock_check_to_cook(cook: Parent) -> None:
    """Send the Sunday stock-check prompt to a single cook.

    Extracted so tests can drive a per-cook send without needing
    visibility from a fresh session. The aggregator below loops over
    every cook and calls this helper.
    """
    from app.services.voice_reply import send_voice_or_text

    await send_voice_or_text(
        cook.whatsapp_id,
        voice_text=_SUNDAY_STOCK_VOICE,
        text_caption=_SUNDAY_STOCK_TEXT,
        language=cook.language or "hi",
    )


async def _send_all_sunday_stock_checks():
    """For every active cook in the database, send the Sunday stock-check prompt."""
    async with async_session() as db:
        result = await db.execute(
            select(Parent).where(
                Parent.role == "cook",
                Parent.is_active.is_(True),
            )
        )
        cooks = result.scalars().all()

        for cook in cooks:
            try:
                await send_sunday_stock_check_to_cook(cook)
            except Exception:  # noqa: BLE001 — one cook's failure must not block the rest
                logger.exception("Sunday stock check failed for cook %s", cook.id)


async def _send_all_attendance_checkins():
    """For every cook, send the 3-button morning check-in (skip if already declared)."""
    from app.services.attendance import (
        needs_morning_checkin,
        send_morning_checkin,
    )

    async with async_session() as db:
        result = await db.execute(
            select(Parent).where(
                Parent.role == "cook",
                Parent.is_active.is_(True),
            )
        )
        cooks = result.scalars().all()

        for cook in cooks:
            try:
                if not await needs_morning_checkin(cook, db):
                    continue
                await send_morning_checkin(cook)
            except Exception:  # noqa: BLE001 — one failed cook must not block the rest
                logger.exception("Attendance check-in failed for cook %s", cook.id)


# ---------------------------------------------------------------------------
# Cook Morning Briefing
# ---------------------------------------------------------------------------

async def _send_all_morning_briefings():
    """Send morning briefing to every active cook across all families."""
    async with async_session() as db:
        result = await db.execute(
            select(Parent).where(
                Parent.role == "cook",
                Parent.is_active.is_(True),
            )
        )
        cooks = result.scalars().all()

        for cook in cooks:
            try:
                await _send_cook_morning_briefing(cook, db)
            except Exception:
                logger.exception("Failed morning briefing for cook %s", cook.id)


async def _send_cook_morning_briefing(cook: Parent, db):
    """Compose and send the morning briefing to a single cook."""
    from app.services.comm_adapter import get_or_create_profile
    from app.services.instruction_engine import get_todays_instructions
    from app.services.whatsapp import send_text_message

    profile = await get_or_create_profile(cook.family_id, "parent", cook.id, db)

    today = date.today()
    sections = []

    greeting = f"Namaste {cook.name} ji! Aaj ka plan:"
    if profile.is_english_dominant:
        greeting = f"Good morning {cook.name}! Today's plan:"
    sections.append(greeting)

    # Meals section
    result = await db.execute(
        select(MealLog).where(
            MealLog.family_id == cook.family_id,
            MealLog.date == today,
        ).order_by(MealLog.meal_type)
    )
    today_meals = result.scalars().all()

    try:
        from app.models.meal_plan import MealPlan
        plan_result = await db.execute(
            select(MealPlan).where(
                MealPlan.family_id == cook.family_id,
                MealPlan.date == today,
            )
        )
        plans = plan_result.scalars().all()
    except Exception:
        plans = []

    # Resolve attached recipe links so we can include them in the
    # caption AND lock the plans the moment the brief goes out.
    plan_recipe_links: dict = {}  # plan_id -> RecipeSource
    if plans:
        from app.models.recipe_source import RecipeSource
        recipe_ids = [p.recipe_source_id for p in plans if p.recipe_source_id]
        if recipe_ids:
            res = await db.execute(
                select(RecipeSource).where(RecipeSource.id.in_(recipe_ids))
            )
            plan_recipe_links = {r.id: r for r in res.scalars().all()}

    if plans or today_meals:
        meal_lines = ["\nKHANA:" if not profile.is_english_dominant else "\nMEALS:"]
        for plan in plans:
            dishes = ", ".join(plan.dishes) if hasattr(plan, 'dishes') and plan.dishes else "TBD"
            meal_lines.append(f"- {plan.meal_type.title()}: {dishes}")
            recipe = plan_recipe_links.get(plan.recipe_source_id) if plan.recipe_source_id else None
            if recipe:
                channel_str = f" ({recipe.channel_name})" if recipe.channel_name else ""
                meal_lines.append(f"  📺 Recipe: {recipe.youtube_url}{channel_str}")

        if not plans and today_meals:
            for meal in today_meals:
                dishes = ", ".join(meal.dishes) if meal.dishes else "TBD"
                meal_lines.append(f"- {meal.meal_type.title()}: {dishes}")

        if not plans and not today_meals:
            label = "Abhi decide nahi hua" if not profile.is_english_dominant else "Not decided yet"
            meal_lines.append(f"- {label}")

        sections.append("\n".join(meal_lines))

    # Past notes section — bundle the latest 3 notes per dish across
    # all household members. Captures running preferences ("Anjan
    # wants less salt in poha", "Mayank doesn't eat garlic") so the
    # cook learns once per morning instead of getting a ping every
    # time someone rates a meal. Best-effort: a failure here must not
    # break the briefing, so the whole block is wrapped in try/except.
    try:
        from app.services.dish_notes import (
            format_for_cook_brief,
            list_notes_for_dish,
        )

        # Build a deduped list of dishes mentioned in today's plans.
        # Order preserved by `dict.fromkeys` insertion semantics.
        dishes_today: list[str] = []
        for plan in plans:
            for dish in (getattr(plan, "dishes", None) or []):
                if dish:
                    dishes_today.append(dish)
        if not plans and today_meals:
            for meal in today_meals:
                for dish in (meal.dishes or []):
                    if dish:
                        dishes_today.append(dish)
        seen: list[str] = list(dict.fromkeys(dishes_today))

        per_dish_lines: list[str] = []
        for dish in seen:
            notes = await list_notes_for_dish(
                cook.family_id, dish, db, limit=3,
            )
            if notes:
                per_dish_lines.append(f"\n{dish}:")
                per_dish_lines.extend(format_for_cook_brief(notes))

        if per_dish_lines:
            label = "PAST NOTES:" if profile.is_english_dominant else "PICHLE NOTES:"
            sections.append(f"\n{label}" + "\n".join(per_dish_lines))
    except Exception:  # noqa: BLE001 — best-effort augmentation
        logger.exception("daily-briefing past-notes section failed")

    # Standing instructions section
    instructions = await get_todays_instructions(cook.family_id, db, target_role="cook")
    if instructions:
        task_label = "TASKS:" if profile.is_english_dominant else "TASKS:"
        task_lines = [f"\n{task_label}"]
        for inst in instructions:
            task_lines.append(f"- {inst.to_briefing_line()}")
            inst.last_sent_at = datetime.now(UTC)
        sections.append("\n".join(task_lines))

    # Pending deliveries section
    try:
        from app.models.cart import Cart
        delivery_result = await db.execute(
            select(Cart).where(
                Cart.family_id == cook.family_id,
                Cart.status.in_(["ordered", "out_for_delivery"]),
            )
        )
        pending_carts = delivery_result.scalars().all()
        if pending_carts:
            delivery_label = "GROCERY:" if not profile.is_english_dominant else "DELIVERIES:"
            delivery_lines = [f"\n{delivery_label}"]
            for cart in pending_carts:
                count = cart.item_count or 0
                delivery_lines.append(f"- Delivery aayegi: {count} items")
            sections.append("\n".join(delivery_lines))
    except Exception:  # noqa: BLE001 — best-effort delivery section
        logger.exception("daily-briefing pending-cart section failed")

    footer = "Koi sawaal ho toh poochiye!" if not profile.is_english_dominant else "Let me know if you have questions!"
    sections.append(f"\n{footer}")

    message = "\n".join(sections)

    if profile.preferred_message_length == "brief":
        message = _truncate_briefing(message)

    # F1 fix (multimodal validation): cook briefings go out as voice +
    # text. The voice script is conversational and ends with an
    # acknowledgement ask; the text caption is the bulleted summary.
    voice_script = _briefing_voice_script(
        cook, plans, today_meals, instructions, profile, plan_recipe_links,
    )
    from app.services.voice_reply import send_voice_or_text
    brief_succeeded = False
    try:
        await send_voice_or_text(
            cook.whatsapp_id,
            voice_text=voice_script,
            text_caption=message,
            language=cook.language or "hi",
        )
        brief_succeeded = True
    except Exception:  # noqa: BLE001 — voice failure must not break briefing
        logger.exception("Voice briefing failed for cook %s — using text fallback", cook.id)
        try:
            await send_text_message(cook.whatsapp_id, message)
            brief_succeeded = True
        except Exception:  # noqa: BLE001
            logger.exception("Text fallback briefing also failed for cook %s", cook.id)

    # Lock the recipe pin on every plan whose link we just delivered.
    # We only lock on a successful send so a transient WhatsApp failure
    # doesn't strand the household in a state where they can't switch
    # the recipe even though the cook never received it.
    if brief_succeeded and plans:
        from app.services.recipe_link_service import lock_plan_recipe
        for plan in plans:
            if plan.recipe_source_id:
                try:
                    await lock_plan_recipe(plan=plan, db=db)
                except Exception:  # noqa: BLE001
                    logger.exception("recipe lock failed for plan %s", plan.id)

    await db.commit()
    logger.info("Morning briefing sent to cook %s", cook.name)


def _briefing_voice_script(
    cook, plans, today_meals, instructions, profile, plan_recipe_links=None,
) -> str:
    """Compose the conversational voice script for the cook morning brief.

    The script is:
      - one greeting line (warm, by name)
      - one meal line per planned meal (or a single line if nothing decided)
      - a one-liner mentioning the recipe link in the text caption when
        any plan has one pinned (cooks listen, then look at the text)
      - one task line per critical/important standing instruction
      - a closing ask: "theek hai? Reply karein agar koi sawaal ho."

    Kept short on purpose — voice attention spans on WhatsApp are ~30 sec.
    """
    plan_recipe_links = plan_recipe_links or {}

    if profile.is_english_dominant:
        lines = [f"Good morning {cook.name}!"]
    else:
        lines = [f"Namaste {cook.name} ji!"]

    if plans:
        for plan in plans:
            dishes = ", ".join(plan.dishes) if hasattr(plan, "dishes") and plan.dishes else "TBD"
            meal_label = plan.meal_type.title()
            if profile.is_english_dominant:
                lines.append(f"{meal_label} mein {dishes} banane hain.")
            else:
                lines.append(f"Aaj {meal_label.lower()} mein {dishes} banaiye.")

        if any(p.recipe_source_id and plan_recipe_links.get(p.recipe_source_id) for p in plans):
            if profile.is_english_dominant:
                lines.append("Recipe link niche bhej diya hai, dekh lijiye.")
            else:
                lines.append("Recipe ka video link niche bheja hai, dekh lijiyega.")
    elif today_meals:
        for meal in today_meals:
            dishes = ", ".join(meal.dishes) if meal.dishes else "TBD"
            lines.append(f"Aaj {meal.meal_type} mein {dishes} banaiye.")
    else:
        lines.append("Aaj ka menu abhi finalise nahi hua hai. Hum thodi der mein bata denge.")

    if instructions:
        critical_instructions = [
            i for i in instructions if i.priority in ("critical", "important")
        ][:2]  # keep voice short — only top 2 in audio, rest in text caption
        for inst in critical_instructions:
            lines.append(f"Yaad rakhiye: {inst.instruction_text}.")

    lines.append("Theek hai? Koi sawaal ho toh reply kar dijiye.")
    return " ".join(lines)


# ---------------------------------------------------------------------------
# User Meal Expectations
# ---------------------------------------------------------------------------

async def _send_all_meal_expectations():
    """Send morning meal expectations to all family approvers."""
    async with async_session() as db:
        result = await db.execute(select(Family))
        families = result.scalars().all()

        for family in families:
            try:
                await _send_meal_expectations(family, db)
            except Exception:
                logger.exception("Failed meal expectations for family %s", family.id)


async def _send_meal_expectations(family: Family, db):
    """Send today's meal expectations as push notification."""
    from app.services.notification import notify_family_children

    today = date.today()

    try:
        from app.models.meal_plan import MealPlan
        result = await db.execute(
            select(MealPlan).where(
                MealPlan.family_id == family.id,
                MealPlan.date == today,
            ).order_by(MealPlan.meal_type)
        )
        plans = result.scalars().all()
    except Exception:
        plans = []

    if not plans:
        return

    lines = [f"Today's meals ({today.strftime('%A')}):"]
    for plan in plans:
        dishes = ", ".join(plan.dishes) if hasattr(plan, 'dishes') and plan.dishes else "TBD"
        lines.append(f"• {plan.meal_type.title()}: {dishes}")

    await notify_family_children(
        family.id,
        "Today's Meal Plan",
        "\n".join(lines),
        data={"type": "meal_expectations", "date": today.isoformat()},
        db=db,
    )


# ---------------------------------------------------------------------------
# Evening Preview (tomorrow's breakfast)
# ---------------------------------------------------------------------------

async def _send_all_evening_previews():
    """Send tomorrow's breakfast preview to all families."""
    async with async_session() as db:
        result = await db.execute(select(Family))
        families = result.scalars().all()

        for family in families:
            try:
                await _send_evening_preview(family, db)
            except Exception:
                logger.exception("Failed evening preview for family %s", family.id)


async def _send_evening_preview(family: Family, db):
    """Send tomorrow's breakfast plan as push notification."""
    from app.services.instruction_engine import get_todays_instructions
    from app.services.notification import notify_family_children

    tomorrow = date.today() + timedelta(days=1)

    try:
        from app.models.meal_plan import MealPlan
        result = await db.execute(
            select(MealPlan).where(
                MealPlan.family_id == family.id,
                MealPlan.date == tomorrow,
                MealPlan.meal_type == "breakfast",
            )
        )
        plan = result.scalar_one_or_none()
    except Exception:
        plan = None

    if not plan:
        return

    dishes = ", ".join(plan.dishes) if hasattr(plan, 'dishes') and plan.dishes else "TBD"
    body = f"Tomorrow's breakfast: {dishes}"

    instructions = await get_todays_instructions(family.id, db, target_role="cook")
    prep_instructions = [
        i for i in instructions
        if i.structured_action and i.structured_action.get("related_meal") == "breakfast"
    ]
    if prep_instructions:
        body += "\nPrep tonight: " + ", ".join(i.instruction_text for i in prep_instructions)

    await notify_family_children(
        family.id,
        "Tomorrow's Breakfast Plan",
        body,
        data={"type": "evening_preview", "date": tomorrow.isoformat()},
        db=db,
    )


# ---------------------------------------------------------------------------
# End-of-Day Summary
# ---------------------------------------------------------------------------

async def _send_all_eod_summaries():
    """Send end-of-day summary to all families."""
    async with async_session() as db:
        result = await db.execute(select(Family))
        families = result.scalars().all()

        for family in families:
            try:
                await _send_eod_summary(family, db)
            except Exception:
                logger.exception("Failed EOD summary for family %s", family.id)


async def _send_eod_summary(family: Family, db):
    """Compose and send the end-of-day summary."""
    from app.services.notification import notify_family_children

    today = date.today()
    lines = [f"Today's summary ({today.strftime('%A')}):"]

    result = await db.execute(
        select(MealLog).where(
            MealLog.family_id == family.id,
            MealLog.date == today,
        )
    )
    meals = result.scalars().all()

    if meals:
        for meal in meals:
            dishes = ", ".join(meal.dishes) if meal.dishes else "—"
            rating_str = f" (rated {meal.rating}/5)" if meal.rating else ""
            lines.append(f"• {meal.meal_type.title()}: {dishes}{rating_str}")
    else:
        lines.append("• No meals logged today")

    instructions_result = await db.execute(
        select(StandingInstruction).where(
            StandingInstruction.family_id == family.id,
            StandingInstruction.status == "active",
        )
    )
    instructions = [i for i in instructions_result.scalars().all() if i.applies_today()]
    completed = sum(1 for i in instructions if i.last_completed_at and i.last_completed_at.date() == today)
    if instructions:
        lines.append(f"• Instructions: {completed}/{len(instructions)} completed")

    if len(lines) <= 1:
        return

    await notify_family_children(
        family.id,
        "Daily Summary",
        "\n".join(lines),
        data={"type": "eod_summary", "date": today.isoformat()},
        db=db,
    )


# ---------------------------------------------------------------------------
# Weekly Digest
# ---------------------------------------------------------------------------

async def _send_all_weekly_digests():
    """Send weekly digest to all families."""
    async with async_session() as db:
        result = await db.execute(select(Family))
        families = result.scalars().all()

        for family in families:
            try:
                await _send_weekly_digest(family, db)
            except Exception:
                logger.exception("Failed weekly digest for family %s", family.id)


async def _send_weekly_digest(family: Family, db):
    """Compose and send the weekly digest."""
    from app.services.notification import notify_family_children

    week_start = date.today() - timedelta(days=7)
    lines = [f"Weekly digest ({week_start.isoformat()} to {date.today().isoformat()}):"]

    result = await db.execute(
        select(MealLog).where(
            MealLog.family_id == family.id,
            MealLog.date >= week_start,
            MealLog.rating.isnot(None),
        )
    )
    rated_meals = result.scalars().all()

    if rated_meals:
        avg_rating = sum(m.rating for m in rated_meals) / len(rated_meals)
        lines.append(f"• Average meal rating: {avg_rating:.1f}/5 ({len(rated_meals)} rated)")

        top_dishes = sorted(rated_meals, key=lambda m: m.rating or 0, reverse=True)[:3]
        top_names = [", ".join(m.dishes[:2]) if m.dishes else "?" for m in top_dishes]
        lines.append(f"• Top rated: {', '.join(top_names)}")

    instructions_result = await db.execute(
        select(StandingInstruction).where(
            StandingInstruction.family_id == family.id,
            StandingInstruction.status == "active",
        )
    )
    instructions = instructions_result.scalars().all()
    if instructions:
        avg_compliance = sum(i.compliance_rate for i in instructions) / len(instructions)
        lines.append(f"• Instruction compliance: {avg_compliance:.0%} average")

    from app.models.improvement_log import ProactiveSuggestion
    suggestions_result = await db.execute(
        select(ProactiveSuggestion).where(
            ProactiveSuggestion.family_id == family.id,
            ProactiveSuggestion.status == "pending",
        )
    )
    pending_suggestions = suggestions_result.scalars().all()
    if pending_suggestions:
        lines.append(f"• {len(pending_suggestions)} improvement suggestions waiting for you")

    if len(lines) <= 1:
        return

    await notify_family_children(
        family.id,
        "Weekly Digest",
        "\n".join(lines),
        data={"type": "weekly_digest"},
        db=db,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _truncate_briefing(message: str, max_lines: int = 15) -> str:
    """Truncate a briefing message for brief-preference profiles."""
    lines = message.split("\n")
    if len(lines) <= max_lines:
        return message
    return "\n".join(lines[:max_lines]) + "\n..."


# ---------------------------------------------------------------------------
# Meal Ready Check (cook confirmation via WhatsApp)
# ---------------------------------------------------------------------------

async def _check_meal_ready_status():
    """Transition plans to COOKING and send ready-check prompts to cooks."""
    from app.services.meal_ready_check import (
        check_and_send_ready_prompts,
        check_stale_cooking_plans,
        transition_to_cooking,
    )

    async with async_session() as db:
        try:
            await transition_to_cooking(db)
        except Exception:
            logger.exception("Failed transition_to_cooking")

        try:
            await check_and_send_ready_prompts(db)
        except Exception:
            logger.exception("Failed check_and_send_ready_prompts")

        try:
            await check_stale_cooking_plans(db)
        except Exception:
            logger.exception("Failed check_stale_cooking_plans")
