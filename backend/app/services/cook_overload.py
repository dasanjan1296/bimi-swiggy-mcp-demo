"""Cook-overload detection — guard against briefing the cook for more
work than she can fit in her slot.

Concrete failure mode the brief calls out:

    "Detect overload (too many dishes vs cook capacity)"

Real-world example: the family votes for chole + bhature + raita +
gulab jamun for one Sunday lunch. Cumulative cook time ≈ 110 min;
Malti didi's slot is 60 min. Without this check, Bimi happily briefs
all four and the cook either gives up halfway or works overtime.

The check is intentionally simple and runs synchronously inside the
briefing pipeline. We do NOT autonomously drop dishes; we surface the
warning to the family with the lowest-priority items pre-selected for
removal, and let the family approve.

Inputs:
  - planned_dishes: list[dict] each with "name" and either
    "estimated_cook_time_mins" or a recipe lookup we can use to fill it.
  - slot_minutes: int (the cook's available time for this meal).

Output:
  - OverloadResult(is_overloaded, total_minutes, suggested_drops,
    headroom_minutes).
"""

from __future__ import annotations

from dataclasses import dataclass

# Conservative defaults when a recipe's cook time is missing. These
# match the rough averages from the meal_engine MOCK catalogue.
_DEFAULT_COOK_TIME_MIN = 30
_BUFFER_MINUTES = 10  # padding for plating + serving + small cleanup


@dataclass
class OverloadResult:
    is_overloaded: bool
    total_minutes: int
    headroom_minutes: int  # negative when overloaded
    suggested_drops: list[str]  # dish names to drop, lowest-priority first


def detect_cook_overload(
    planned_dishes: list[dict],
    slot_minutes: int,
    *,
    side_dish_names: tuple[str, ...] = ("raita", "salad", "papad", "achar", "chutney"),
) -> OverloadResult:
    """Compute whether the planned briefing exceeds the cook's slot.

    Side dishes (raita, salad, etc.) are tagged for removal first
    because they're trivially substitutable. Sweets and biryanis are
    last to drop.
    """
    enriched: list[tuple[dict, int, bool]] = []  # (dish, minutes, is_side)
    for dish in planned_dishes:
        mins = dish.get("estimated_cook_time_mins")
        if mins is None:
            mins = _DEFAULT_COOK_TIME_MIN
        name_l = dish.get("name", "").lower()
        is_side = any(side in name_l for side in side_dish_names)
        enriched.append((dish, int(mins), is_side))

    total = sum(m for _, m, _ in enriched) + _BUFFER_MINUTES
    headroom = slot_minutes - total

    if headroom >= 0:
        return OverloadResult(
            is_overloaded=False,
            total_minutes=total,
            headroom_minutes=headroom,
            suggested_drops=[],
        )

    # Overloaded — pick a drop set. Strategy:
    # 1. Drop sides first (cheapest to remove, family least cares).
    # 2. If still over, drop the longest-cooking remaining dish.
    drops: list[str] = []
    saved = 0
    overage = -headroom

    for dish, mins, _is_side in sorted(enriched, key=lambda e: (not e[2], -e[1])):
        if saved >= overage:
            break
        drops.append(dish.get("name", "Unknown"))
        saved += mins

    return OverloadResult(
        is_overloaded=True,
        total_minutes=total,
        headroom_minutes=headroom,
        suggested_drops=drops,
    )


def format_overload_warning(result: OverloadResult, slot_minutes: int) -> str:
    """Render the warning message for the family-side notification."""
    drops_text = ", ".join(result.suggested_drops) or "kuch nahi"
    return (
        f"⚠️ Yeh zyada lag raha hai didi ke liye:\n"
        f"Total time: ~{result.total_minutes} min\n"
        f"Slot: {slot_minutes} min\n\n"
        f"Suggest karte hain: *{drops_text}* hata dein. "
        f"Ya didi ko thoda extra time dein."
    )
