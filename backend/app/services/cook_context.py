"""
Cook Context Resolver — determines which household a shared cook's message
belongs to, using a priority-based resolution strategy.

Resolution priority:
  1. Explicit mention  — cook names a household in the message text
  2. Active confirmation — an in-flight confirmation flow pins the context
  3. Schedule match    — current time falls within a known slot for one household
  4. Recency           — last interaction within a 2-hour window
  5. Disambiguation    — send an interactive button picker to the cook

Also handles broadcast intents (e.g. "kal nahi aa paungi" → all homes).
"""

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.confirmation import ConfirmationState, PendingConfirmation
from app.models.family import Parent
from app.models.shared_cook import SharedCook, SharedCookHousehold

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

WEEKDAY_MAP = {
    0: "monday",
    1: "tuesday",
    2: "wednesday",
    3: "thursday",
    4: "friday",
    5: "saturday",
    6: "sunday",
}


@dataclass
class ResolvedContext:
    """Result of household resolution for a shared cook message."""

    cook: SharedCook
    family_id: uuid.UUID | None
    household_label: str | None
    parent: Parent | None
    resolution_method: str  # explicit | confirmation | schedule | recency | ambiguous
    is_broadcast: bool = False
    all_family_ids: list[uuid.UUID] | None = None


async def lookup_shared_cook(wa_id: str, db: AsyncSession) -> SharedCook | None:
    result = await db.execute(
        select(SharedCook).where(SharedCook.whatsapp_id == wa_id)
    )
    return result.scalar_one_or_none()


async def _load_active_households(
    cook: SharedCook, db: AsyncSession,
) -> list[SharedCookHousehold]:
    """Explicit query for a cook's active households.

    SQLAlchemy async cannot lazy-load relationships, so any direct access to
    `cook.households` raises `MissingGreenlet`. This helper is the ONLY
    sanctioned way to fetch a cook's households inside an async session.
    """
    result = await db.execute(
        select(SharedCookHousehold).where(
            SharedCookHousehold.cook_id == cook.id,
            SharedCookHousehold.is_active.is_(True),
        )
    )
    return list(result.scalars().all())


async def resolve_household(
    cook: SharedCook,
    message_text: str | None,
    db: AsyncSession,
) -> ResolvedContext:
    """
    Walk the priority chain to determine which household this message targets.
    Returns a ResolvedContext with the resolved family_id (or None if ambiguous).
    """
    active_households = await _load_active_households(cook, db)

    if not active_households:
        return ResolvedContext(
            cook=cook,
            family_id=None,
            household_label=None,
            parent=None,
            resolution_method="no_households",
        )

    if len(active_households) == 1:
        hh = active_households[0]
        parent = await _get_parent_for_family(cook.whatsapp_id, hh.family_id, db)
        return ResolvedContext(
            cook=cook,
            family_id=hh.family_id,
            household_label=hh.household_label,
            parent=parent,
            resolution_method="single_household",
        )

    all_ids = [h.family_id for h in active_households]

    # 1. Explicit mention
    if message_text:
        match = _match_explicit_household(message_text, active_households)
        if match:
            parent = await _get_parent_for_family(cook.whatsapp_id, match.family_id, db)
            return ResolvedContext(
                cook=cook,
                family_id=match.family_id,
                household_label=match.household_label,
                parent=parent,
                resolution_method="explicit",
            )

    # 2. Active confirmation flow
    confirmed = await _check_active_confirmation(cook.whatsapp_id, active_households, db)
    if confirmed:
        hh = next(h for h in active_households if h.family_id == confirmed)
        parent = await _get_parent_for_family(cook.whatsapp_id, confirmed, db)
        return ResolvedContext(
            cook=cook,
            family_id=confirmed,
            household_label=hh.household_label,
            parent=parent,
            resolution_method="confirmation",
        )

    # 3. Schedule match
    scheduled = _match_schedule(active_households)
    if scheduled and len(scheduled) == 1:
        hh = scheduled[0]
        parent = await _get_parent_for_family(cook.whatsapp_id, hh.family_id, db)
        return ResolvedContext(
            cook=cook,
            family_id=hh.family_id,
            household_label=hh.household_label,
            parent=parent,
            resolution_method="schedule",
        )

    # 4. Recency — last switched within 2 hours
    if cook.active_family_id and cook.last_switched_at:
        cutoff = datetime.now(UTC) - timedelta(hours=2)
        if cook.last_switched_at >= cutoff:
            hh = next(
                (h for h in active_households if h.family_id == cook.active_family_id),
                None,
            )
            if hh:
                parent = await _get_parent_for_family(cook.whatsapp_id, hh.family_id, db)
                return ResolvedContext(
                    cook=cook,
                    family_id=hh.family_id,
                    household_label=hh.household_label,
                    parent=parent,
                    resolution_method="recency",
                )

    # 5. Ambiguous — caller must send disambiguation buttons
    return ResolvedContext(
        cook=cook,
        family_id=None,
        household_label=None,
        parent=None,
        resolution_method="ambiguous",
        all_family_ids=all_ids,
    )


async def switch_active_household(
    cook: SharedCook,
    family_id: uuid.UUID,
    db: AsyncSession,
) -> SharedCookHousehold | None:
    """Explicitly set the cook's active household and update timestamp."""
    result = await db.execute(
        select(SharedCookHousehold).where(
            SharedCookHousehold.cook_id == cook.id,
            SharedCookHousehold.family_id == family_id,
            SharedCookHousehold.is_active.is_(True),
        )
    )
    hh = result.scalar_one_or_none()
    if not hh:
        return None
    cook.active_family_id = family_id
    cook.last_switched_at = datetime.now(UTC)
    await db.flush()
    return hh


async def get_active_households(
    cook: SharedCook, db: AsyncSession,
) -> list[SharedCookHousehold]:
    """Return the cook's active households via an explicit query.

    `db` is required — there is no lazy-load fallback because async
    SQLAlchemy can't satisfy one without greenlet-spawn, and we want
    every caller to be honest about its session usage.
    """
    return await _load_active_households(cook, db)


async def get_household_label_for_parent(
    parent: Parent, db: AsyncSession,
) -> str | None:
    """
    If this parent is a shared cook, return the household label for their current
    family. Returns None for single-household users (no prefix needed).
    """
    cook = await lookup_shared_cook(parent.whatsapp_id, db)
    if not cook:
        return None
    active = await _load_active_households(cook, db)
    if len(active) <= 1:
        return None
    hh = next((h for h in active if h.family_id == parent.family_id), None)
    return hh.household_label if hh else None


def household_label_prefix(label: str) -> str:
    """Format a household label for message prefixing: [🏠 Flat 114]"""
    return f"[🏠 {label}]"


def household_divider(label: str) -> str:
    """Full-width divider sent when context switches."""
    return f"━━━━ 🏠 {label} ━━━━"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _match_explicit_household(
    text: str, households: list[SharedCookHousehold],
) -> SharedCookHousehold | None:
    """
    Check if the cook's message explicitly names a household.
    Matches against the household_label and common short-forms like "#114".
    """
    text_lower = text.lower().strip()

    for hh in households:
        label_lower = hh.household_label.lower()
        if label_lower in text_lower:
            return hh

        numbers = re.findall(r"\d+", hh.household_label)
        for num in numbers:
            if re.search(rf"(?:flat|#)\s*{num}\b", text_lower):
                return hh

    return None


async def _check_active_confirmation(
    wa_id: str,
    households: list[SharedCookHousehold],
    db: AsyncSession,
) -> uuid.UUID | None:
    """If the cook has an in-flight confirmation for one household, stick to it."""
    family_ids = [h.family_id for h in households]

    parents = await db.execute(
        select(Parent).where(
            and_(Parent.whatsapp_id == wa_id, Parent.family_id.in_(family_ids))
        )
    )
    parent_rows = parents.scalars().all()
    parent_ids = [p.id for p in parent_rows]
    if not parent_ids:
        return None

    result = await db.execute(
        select(PendingConfirmation).where(
            and_(
                PendingConfirmation.parent_id.in_(parent_ids),
                PendingConfirmation.state.notin_([
                    ConfirmationState.RESOLVED,
                    ConfirmationState.EXPIRED,
                ]),
            )
        ).limit(1)
    )
    active = result.scalar_one_or_none()
    if active:
        return active.family_id
    return None


def _match_schedule(
    households: list[SharedCookHousehold],
) -> list[SharedCookHousehold]:
    """Return households whose schedule slots include the current IST time."""
    now = datetime.now(IST)
    current_day = WEEKDAY_MAP[now.weekday()]
    current_minutes = now.hour * 60 + now.minute

    matches: list[SharedCookHousehold] = []

    for hh in households:
        slots = hh.schedule_slots
        if not slots or not isinstance(slots, list):
            continue
        for slot in slots:
            days = slot.get("days", [])
            if current_day not in [d.lower() for d in days]:
                continue
            arrival = _parse_time_minutes(slot.get("arrival"))
            departure = _parse_time_minutes(slot.get("departure"))
            if arrival is not None and departure is not None:
                if arrival <= current_minutes <= departure:
                    matches.append(hh)
                    break

    return matches


def _parse_time_minutes(t: str | None) -> int | None:
    """Parse 'HH:MM' or 'H:MM' to minutes since midnight."""
    if not t:
        return None
    try:
        parts = t.split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, IndexError):
        return None


async def _get_parent_for_family(
    wa_id: str, family_id: uuid.UUID, db: AsyncSession,
) -> Parent | None:
    result = await db.execute(
        select(Parent).where(
            and_(Parent.whatsapp_id == wa_id, Parent.family_id == family_id)
        )
    )
    return result.scalar_one_or_none()
