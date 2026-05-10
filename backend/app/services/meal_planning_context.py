"""Single source of truth for meal-planning context (G1 + G2 + G3 + G10).

Used by:
  - meal_engine.suggest_meals  -- inject headcount + meal-time-slot into the prompt
  - meal_rag.build_rag_recipe_context -- adjust ranking by these signals
  - prep_timeline endpoint     -- compute the cook arrival -> prep -> ready chain
  - (future) household-cook briefing -- show "Cook for 4 today, not 6 (Akhil away on WFO)"

Everything is read-only here; no DB writes. Functions:
  - `eaters_for_meal(family, meal_type, day)` -> list[PersonContext who is home]
  - `meal_slots(family)` -> {"breakfast":"07:30","lunch":"13:00",...}
  - `effective_headcount(family, meal_type, day)` -> float (sums portion_multiplier)
  - `scaled_total_time(recipe, headcount)` -> int minutes
  - `prep_chain(family, day, meal_type, recipe)` -> dict timeline
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.context import FamilyContext
from app.models.person_context import PersonContext

logger = logging.getLogger(__name__)


# G2: defaults. Updated per-family via FamilyContext.meal_time_slots.
DEFAULT_MEAL_SLOTS = {
    "breakfast": "07:30",
    "lunch": "13:00",
    "dinner": "20:00",
    "snack": "17:00",
}

WEEKDAY_SHORT = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


# ---------------------------------------------------------------------------
# G2: meal-time slots per family
# ---------------------------------------------------------------------------

async def meal_slots(family_id: uuid.UUID, db: AsyncSession) -> dict[str, str]:
    """Return {"breakfast":"07:30","lunch":"13:00",...} for this family.

    Falls back to DEFAULT_MEAL_SLOTS for any meal-type the family hasn't
    customised.
    """
    fc = (await db.execute(
        select(FamilyContext).where(FamilyContext.family_id == family_id)
    )).scalar_one_or_none()
    out = dict(DEFAULT_MEAL_SLOTS)
    if fc and fc.meal_time_slots:
        out.update({k: str(v) for k, v in fc.meal_time_slots.items()})
    return out


def slot_as_time(slot_str: str) -> time:
    """Parse 'HH:MM' to a `time`. Tolerates extra whitespace + leading 0 omission."""
    s = slot_str.strip()
    if ":" not in s:
        return time.fromisoformat("12:00")
    parts = s.split(":")
    h = int(parts[0])
    m = int(parts[1]) if len(parts) > 1 else 0
    return time(hour=h % 24, minute=m % 60)


# ---------------------------------------------------------------------------
# G1: schedule-aware headcount
# ---------------------------------------------------------------------------

def _is_member_present_today(person: PersonContext, target_day: date, meal_type: str) -> bool:
    """Apply PersonContext.schedule_rules to decide if the eater is home for this meal.

    schedule_rules format:
      [
        {"rule": "WFO Tue/Thu", "impact": "skip lunch at home", "days": ["tue", "thu"]},
        {"rule": "Gym 6-7 AM", "impact": "needs protein", "days": ["mon","wed","fri"]},
        {"rule": "Out for dinner Wed", "impact": "skip dinner", "days": ["wed"]},
      ]

    We look for impact substrings: 'skip lunch', 'skip breakfast', 'skip dinner',
    'away', 'wfo', 'travel'. Matched + day matches = mark absent for that meal.
    """
    if not person.schedule_rules:
        return True
    today_short = WEEKDAY_SHORT[target_day.weekday()]
    for rule in person.schedule_rules:
        days = [(d or "").lower()[:3] for d in (rule.get("days") or [])]
        if today_short not in days:
            continue
        impact = (rule.get("impact") or "").lower()
        if "skip " + meal_type in impact:
            return False
        if meal_type == "lunch" and ("wfo" in impact or "office" in impact):
            return False
        if "travel" in impact or "out of town" in impact:
            return False
    return True


async def eaters_for_meal(
    family_id: uuid.UUID, meal_type: str, target_day: date, db: AsyncSession,
) -> list[PersonContext]:
    """All household members expected to eat this meal on this day."""
    persons = (await db.execute(
        select(PersonContext).where(
            PersonContext.family_id == family_id,
            PersonContext.is_active.is_(True),
        )
    )).scalars().all()
    return [p for p in persons if _is_member_present_today(p, target_day, meal_type)]


async def effective_headcount(
    family_id: uuid.UUID, meal_type: str, target_day: date, db: AsyncSession,
) -> float:
    """Headcount weighted by per-eater portion_multiplier.

    Examples:
      - 4 adults all 1.0 -> 4.0
      - 2 adults 1.0, 1 elder 0.7, 1 kid 0.5 -> 3.2
      - same family with elder out (schedule rule) for dinner -> 2.5
    """
    eaters = await eaters_for_meal(family_id, meal_type, target_day, db)
    return sum((e.portion_multiplier or 1.0) for e in eaters) or 1.0


async def headcount_summary(
    family_id: uuid.UUID, meal_type: str, target_day: date, db: AsyncSession,
) -> dict:
    """For prompt + UI -- one structured summary of who's eating today."""
    eaters = await eaters_for_meal(family_id, meal_type, target_day, db)
    all_persons = (await db.execute(
        select(PersonContext).where(
            PersonContext.family_id == family_id,
            PersonContext.is_active.is_(True),
        )
    )).scalars().all()
    absent = [p.person_name for p in all_persons if p not in eaters]
    return {
        "headcount": len(eaters),
        "effective_portions": round(sum((e.portion_multiplier or 1.0) for e in eaters), 2),
        "present_names": [e.person_name for e in eaters],
        "absent_names": absent,
        "absence_reason_seen": bool(absent),
    }


# ---------------------------------------------------------------------------
# G3: scaled prep + cook time
# ---------------------------------------------------------------------------

PREP_OVERHEAD_FRACTION = 0.30  # 30% of prep time is fixed overhead, doesn't scale linearly
COOK_OVERHEAD_FRACTION = 0.40  # cooking: 40% fixed (heating + simmering), 60% scales


def scaled_total_time(recipe, headcount_portions: float) -> int:
    """Predict total wall-clock time in minutes for this recipe scaled to
    `headcount_portions` (sum of portion multipliers).

    Recipe carries `prep_time_mins` + `cook_time_mins` defined for `default_servings`.
    We linearly interpolate with a fixed-overhead floor so cooking dal for 6
    isn't 3x as long as for 2, but it's still longer.
    """
    prep = int(getattr(recipe, "prep_time_mins", 0) or 0)
    cook = int(getattr(recipe, "cook_time_mins", 0) or 0)
    default_servings = max(1, int(getattr(recipe, "default_servings", 4) or 4))
    if headcount_portions <= 0:
        headcount_portions = float(default_servings)

    scale = headcount_portions / default_servings
    prep_scaled = prep * (PREP_OVERHEAD_FRACTION + (1 - PREP_OVERHEAD_FRACTION) * scale)
    cook_scaled = cook * (COOK_OVERHEAD_FRACTION + (1 - COOK_OVERHEAD_FRACTION) * scale)
    return int(round(prep_scaled + cook_scaled))


# ---------------------------------------------------------------------------
# G10: cook arrival -> prep -> ready timeline
# ---------------------------------------------------------------------------

async def prep_chain(
    family_id: uuid.UUID,
    target_day: date,
    meal_type: str,
    recipe,
    db: AsyncSession,
    cook_arrival: time | None = None,
) -> dict:
    """Build a structured timeline:
       cook_arrival -> prep_start -> cook_start -> ready_at  (all on target_day).

    `cook_arrival` defaults to 30 min before the configured meal slot's
    prep window. If recipe has advance_prep (soaking etc.), we add a
    'previous-day prep' note.
    """
    slots = await meal_slots(family_id, db)
    slot = slot_as_time(slots.get(meal_type, DEFAULT_MEAL_SLOTS.get(meal_type, "13:00")))
    headcount = await effective_headcount(family_id, meal_type, target_day, db)
    total_min = scaled_total_time(recipe, headcount)
    prep_min = int(getattr(recipe, "prep_time_mins", 0) or 0)
    # Cook arrival = prep_min before the cook actually starts cooking (some
    # families want cook to arrive 15 min ahead of prep_start for setup).
    setup_buffer_min = 10

    # Work backward from the meal slot.
    # ready_at = slot. cook ends -> ready_at - 5 min plating buffer.
    plating_buffer_min = 5
    ready_at = datetime.combine(target_day, slot, tzinfo=UTC)
    cook_start = ready_at - timedelta(minutes=plating_buffer_min)
    cook_end = cook_start  # cook_start is when active cooking begins; cook_end == ready_at - plating_buffer
    cook_duration = max(0, total_min - prep_min)
    prep_start = cook_start - timedelta(minutes=prep_min)
    if cook_arrival is None:
        cook_arrival_dt = prep_start - timedelta(minutes=setup_buffer_min)
    else:
        cook_arrival_dt = datetime.combine(target_day, cook_arrival, tzinfo=UTC)

    advance = bool(getattr(recipe, "advance_prep_note", None))
    advance_note = getattr(recipe, "advance_prep_note", None)

    return {
        "meal_type": meal_type,
        "headcount_portions": round(headcount, 2),
        "total_time_min": total_min,
        "ready_at": ready_at.isoformat(),
        "cook_start": cook_start.isoformat(),
        "prep_start": prep_start.isoformat(),
        "cook_arrival": cook_arrival_dt.isoformat(),
        "advance_prep_required": advance,
        "advance_prep_note": advance_note,
        "previous_day_action": (
            f"Tonight: {advance_note}" if advance else None
        ),
    }


# ---------------------------------------------------------------------------
# Prompt-context renderer (used by meal_engine)
# ---------------------------------------------------------------------------

async def render_meal_context_block(
    family_id: uuid.UUID, meal_type: str, target_day: date, db: AsyncSession,
) -> str:
    """A short MEAL CONTEXT block to inject into the meal-suggest prompt.

    Combines:
      - meal slot time (G2)
      - effective headcount + present/absent (G1)
      - cook present today
    """
    slots = await meal_slots(family_id, db)
    slot = slots.get(meal_type, DEFAULT_MEAL_SLOTS.get(meal_type, "13:00"))
    summary = await headcount_summary(family_id, meal_type, target_day, db)
    lines = [
        "MEAL CONTEXT:",
        f"  meal slot: {meal_type} @ {slot} IST",
        f"  expected eaters: {summary['headcount']} "
        f"(effective portions: {summary['effective_portions']})",
    ]
    if summary["absent_names"]:
        lines.append(f"  AWAY today: {', '.join(summary['absent_names'])}")
    if summary["present_names"]:
        lines.append(f"  PRESENT: {', '.join(summary['present_names'])}")
    return "\n".join(lines)
