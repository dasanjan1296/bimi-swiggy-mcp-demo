"""
Proactive Pattern Detection — Bimi notices things and suggests improvements.

Runs as a weekly batch job. Detects:
1. Recurring one-off requests -> suggest standing instructions
2. Declining meal ratings -> suggest dish rotation
3. Unused instructions -> suggest check-in or removal
4. Missing meal coverage -> suggest planning
5. Health goal drift -> suggest prioritization
6. Cook skill growth -> celebrate and encourage
"""
import logging
import uuid
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.improvement_log import ProactiveSuggestion
from app.models.meal import MealLog
from app.models.standing_instruction import StandingInstruction

logger = logging.getLogger(__name__)


async def run_pattern_detection(
    family_id: uuid.UUID,
    db: AsyncSession,
) -> list[ProactiveSuggestion]:
    """Run all pattern detectors and return generated suggestions."""
    suggestions = []

    detectors = [
        _detect_recurring_requests,
        _detect_declining_ratings,
        _detect_unused_instructions,
        _detect_missing_meal_coverage,
        _detect_cook_skill_growth,
    ]

    for detector in detectors:
        try:
            new_suggestions = await detector(family_id, db)
            suggestions.extend(new_suggestions)
        except Exception:
            logger.exception("Pattern detector %s failed", detector.__name__)

    return suggestions


async def _detect_recurring_requests(
    family_id: uuid.UUID,
    db: AsyncSession,
) -> list[ProactiveSuggestion]:
    """Find items/actions requested 3+ times that could become standing instructions."""
    from app.models.context import ConversationMessage

    cutoff = datetime.now(UTC) - timedelta(days=30)
    result = await db.execute(
        select(ConversationMessage).where(
            ConversationMessage.family_id == family_id,
            ConversationMessage.created_at >= cutoff,
        )
    )
    messages = result.scalars().all()

    word_counter: Counter = Counter()
    for msg in messages:
        if msg.raw_input:
            words = msg.raw_input.lower().split()
            for bigram in zip(words, words[1:]):
                word_counter[" ".join(bigram)] += 1

    suggestions = []
    threshold = 3

    action_words = {"soak", "clean", "make", "prepare", "boil", "wash", "cut",
                    "bheego", "saaf", "bana", "dhona", "kata", "ubaal"}

    for phrase, count in word_counter.most_common(20):
        if count >= threshold and any(w in phrase for w in action_words):
            existing = await db.execute(
                select(ProactiveSuggestion).where(
                    ProactiveSuggestion.family_id == family_id,
                    ProactiveSuggestion.pattern_type == "recurring_request",
                    ProactiveSuggestion.title.ilike(f"%{phrase}%"),
                    ProactiveSuggestion.status == "pending",
                )
            )
            if existing.scalar_one_or_none():
                continue

            suggestion = ProactiveSuggestion(
                family_id=family_id,
                pattern_type="recurring_request",
                title=f'"{phrase}" has been mentioned {count} times this month',
                description=(
                    f"You've mentioned \"{phrase}\" {count} times in the last 30 days. "
                    "Should I make this a standing instruction for the cook?"
                ),
                evidence={"phrase": phrase, "count": count, "days": 30},
                suggested_action={
                    "type": "create_instruction",
                    "instruction_text": phrase,
                },
                confidence=min(count / 10.0, 0.9),
            )
            db.add(suggestion)
            suggestions.append(suggestion)

    await db.flush()
    return suggestions


async def _detect_declining_ratings(
    family_id: uuid.UUID,
    db: AsyncSession,
) -> list[ProactiveSuggestion]:
    """Find dishes whose ratings have declined over the past 3 weeks."""
    cutoff = date.today() - timedelta(days=21)
    result = await db.execute(
        select(MealLog).where(
            MealLog.family_id == family_id,
            MealLog.date >= cutoff,
            MealLog.rating.isnot(None),
        ).order_by(MealLog.date)
    )
    meals = result.scalars().all()

    dish_ratings: dict[str, list[tuple[date, int]]] = defaultdict(list)
    for meal in meals:
        if isinstance(meal.dishes, list):
            for dish in meal.dishes:
                if meal.rating:
                    dish_ratings[dish.lower()].append((meal.date, meal.rating))

    suggestions = []
    for dish, ratings in dish_ratings.items():
        if len(ratings) < 3:
            continue

        mid = len(ratings) // 2
        early_avg = sum(r for _, r in ratings[:mid]) / mid
        late_avg = sum(r for _, r in ratings[mid:]) / (len(ratings) - mid)

        if early_avg - late_avg >= 1.0:
            suggestion = ProactiveSuggestion(
                family_id=family_id,
                pattern_type="declining_ratings",
                title=f'"{dish}" ratings are declining',
                description=(
                    f"{dish.title()} went from {early_avg:.1f} to {late_avg:.1f} stars "
                    f"over the past 3 weeks. Time to try a new recipe or rotate it out?"
                ),
                evidence={
                    "dish": dish,
                    "early_avg": round(early_avg, 1),
                    "late_avg": round(late_avg, 1),
                    "sample_count": len(ratings),
                },
                suggested_action={
                    "type": "suggest_rotation",
                    "dish": dish,
                },
                confidence=0.7,
            )
            db.add(suggestion)
            suggestions.append(suggestion)

    await db.flush()
    return suggestions


async def _detect_unused_instructions(
    family_id: uuid.UUID,
    db: AsyncSession,
) -> list[ProactiveSuggestion]:
    """Find active instructions that haven't been confirmed in 2+ weeks."""
    cutoff = datetime.now(UTC) - timedelta(days=14)
    result = await db.execute(
        select(StandingInstruction).where(
            StandingInstruction.family_id == family_id,
            StandingInstruction.status == "active",
        )
    )
    instructions = result.scalars().all()

    suggestions = []
    for inst in instructions:
        last_activity = inst.last_completed_at or inst.created_at
        if last_activity and last_activity < cutoff:
            suggestion = ProactiveSuggestion(
                family_id=family_id,
                pattern_type="unused_instruction",
                title=f'"{inst.instruction_text[:50]}" hasn\'t been confirmed in 2 weeks',
                description=(
                    f"The instruction \"{inst.instruction_text}\" hasn't been confirmed "
                    "by the cook in over 2 weeks. Should I check in or pause it?"
                ),
                evidence={
                    "instruction_id": str(inst.id),
                    "instruction_text": inst.instruction_text,
                    "last_completed": last_activity.isoformat() if last_activity else None,
                    "compliance_rate": inst.compliance_rate,
                },
                suggested_action={
                    "type": "check_instruction",
                    "instruction_id": str(inst.id),
                },
                confidence=0.6,
            )
            db.add(suggestion)
            suggestions.append(suggestion)

    await db.flush()
    return suggestions


async def _detect_missing_meal_coverage(
    family_id: uuid.UUID,
    db: AsyncSession,
) -> list[ProactiveSuggestion]:
    """Find days of the week with no meal plans or frequent gaps."""
    cutoff = date.today() - timedelta(days=28)
    result = await db.execute(
        select(MealLog.date, MealLog.meal_type).where(
            MealLog.family_id == family_id,
            MealLog.date >= cutoff,
        )
    )
    meals = result.all()

    day_meal_counts: dict[str, Counter] = defaultdict(Counter)
    for meal_date, meal_type in meals:
        day_name = meal_date.strftime("%A")
        day_meal_counts[day_name][meal_type] += 1

    all_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    suggestions = []

    for day in all_days:
        counts = day_meal_counts.get(day, Counter())
        for meal_type in ["breakfast", "lunch", "dinner"]:
            if counts.get(meal_type, 0) == 0:
                suggestion = ProactiveSuggestion(
                    family_id=family_id,
                    pattern_type="missing_coverage",
                    title=f"No {meal_type} planned on {day}s",
                    description=(
                        f"You haven't had a planned {meal_type} on {day}s in the past "
                        "4 weeks. Would you like to set up a default meal or remind the cook?"
                    ),
                    evidence={"day": day, "meal_type": meal_type, "count": 0},
                    suggested_action={
                        "type": "suggest_default_meal",
                        "day": day,
                        "meal_type": meal_type,
                    },
                    confidence=0.5,
                )
                db.add(suggestion)
                suggestions.append(suggestion)

    await db.flush()
    return suggestions[:5]


async def _detect_cook_skill_growth(
    family_id: uuid.UUID,
    db: AsyncSession,
) -> list[ProactiveSuggestion]:
    """Detect when the cook has successfully prepared new dishes."""
    from app.models.hcg import ContextNode, PreferenceEdge

    cutoff = datetime.now(UTC) - timedelta(days=30)
    result = await db.execute(
        select(PreferenceEdge, ContextNode).join(
            ContextNode, PreferenceEdge.object_node_id == ContextNode.id,
        ).where(
            PreferenceEdge.family_id == family_id,
            PreferenceEdge.relation_type == "CAN_COOK",
            PreferenceEdge.created_at >= cutoff,
            PreferenceEdge.is_active == True,
        )
    )
    new_dishes = result.all()

    if len(new_dishes) >= 3:
        dish_names = [node.name for _, node in new_dishes]
        suggestion = ProactiveSuggestion(
            family_id=family_id,
            pattern_type="cook_skill_growth",
            title=f"Cook has learned {len(new_dishes)} new dishes this month!",
            description=(
                f"Great news! The cook has successfully prepared {len(new_dishes)} "
                f"new dishes this month: {', '.join(dish_names[:5])}. "
                "Their repertoire is growing!"
            ),
            evidence={
                "new_dish_count": len(new_dishes),
                "dishes": dish_names[:10],
            },
            suggested_action={"type": "celebrate"},
            confidence=0.9,
        )
        db.add(suggestion)
        await db.flush()
        return [suggestion]

    return []
