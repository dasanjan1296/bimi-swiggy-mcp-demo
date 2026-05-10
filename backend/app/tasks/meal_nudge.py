"""
Periodic task: send a soft push notification asking the approver to rate today's meals.

Runs ~30 minutes after typical meal times (configurable).
Only nudges once per meal — uses the MealLog.nudge_sent flag.
"""

import asyncio
import logging
from datetime import UTC, date, datetime

from sqlalchemy import and_, select

from app.db import async_session
from app.models.meal import MealLog

logger = logging.getLogger(__name__)

MEAL_NUDGE_HOURS = {
    "breakfast": 9,
    "lunch": 14,
    "dinner": 21,
    "snack": 17,
}


async def _send_nudges():
    async with async_session() as db:
        now = datetime.now(UTC)
        today = date.today()

        eligible_types = [
            mt for mt, hour in MEAL_NUDGE_HOURS.items()
            if now.hour >= hour
        ]

        if not eligible_types:
            return

        result = await db.execute(
            select(MealLog).where(
                and_(
                    MealLog.date == today,
                    MealLog.rating.is_(None),
                    MealLog.nudge_sent.is_(False),
                    MealLog.meal_type.in_(eligible_types),
                )
            )
        )
        meals = list(result.scalars().all())

        if not meals:
            return

        from app.services.notification import notify_family_children

        families_nudged: set = set()
        for meal in meals:
            if meal.family_id in families_nudged:
                meal.nudge_sent = True
                continue

            dishes_str = ", ".join(meal.dishes) if meal.dishes else meal.meal_type
            await notify_family_children(
                family_id=meal.family_id,
                title="How was today's meal?",
                body=f"Rate {dishes_str} — helps us suggest better meals 🍽️",
                data={
                    "type": "meal_feedback",
                    "meal_id": str(meal.id),
                    "meal_type": meal.meal_type,
                },
                db=db,
            )

            meal.nudge_sent = True
            families_nudged.add(meal.family_id)
            logger.info(
                "Sent meal feedback nudge for family %s, meal %s",
                meal.family_id,
                meal.id,
            )

        await db.commit()


def check_meal_nudges():
    """Sync wrapper for APScheduler."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_send_nudges())
        else:
            loop.run_until_complete(_send_nudges())
    except RuntimeError:
        asyncio.run(_send_nudges())
