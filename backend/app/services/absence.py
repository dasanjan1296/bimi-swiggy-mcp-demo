"""
Absence detection and replacement booking service.

When househelp sends "aaj nahi aa paunga", "chutti", "sick", etc.:
1. Detect absence intent from transcript
2. Create HousehelpAbsence record
3. Based on role, suggest replacement options (UC, Snabbit, Swiggy)
4. Send approval card to the approver
5. On approval: generate deep link to replacement platform

Advance notice flow (e.g. "3 din baad chutti leni hai"):
1. Parse future date from message
2. Create HousehelpAbsence with is_advance_notice=True, slot_check_active=True
3. Scheduler starts polling replacement platforms for slot availability
4. When slot found: notify approver with deep link for one-tap booking
"""

import logging
import re
import uuid
from datetime import date, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.family import Parent
from app.models.meal import HousehelpAbsence
from app.services.platforms import get_replacement_options

logger = logging.getLogger(__name__)

ABSENCE_KEYWORDS_HI = [
    "nahi aaunga", "nahi aa paunga", "nahi aa paaungi", "nahi aaungi",
    "chutti", "leave", "not coming", "sick", "beemar",
    "nahi aa sakta", "nahi aa sakti", "cancel", "aaj nahi",
    "tabiyat kharab", "hospital", "emergency",
]

ABSENCE_KEYWORDS_EN = [
    "not coming", "on leave", "sick", "can't come", "won't come",
    "taking off", "day off", "absent", "not available", "emergency",
]

FUTURE_DATE_PATTERNS_HI = {
    r"kal\b": 1,
    r"parso\b": 2,
    r"parson\b": 2,
    r"(\d+)\s*din\s*(?:baad|bad|ke\s*baad)": None,  # N days from now
    r"(\d+)\s*days?\s*(?:later|from\s*now|after)": None,
    r"next\s*(?:monday|mon)": "next_monday",
    r"next\s*(?:tuesday|tue)": "next_tuesday",
    r"next\s*(?:wednesday|wed)": "next_wednesday",
    r"next\s*(?:thursday|thu)": "next_thursday",
    r"next\s*(?:friday|fri)": "next_friday",
    r"next\s*(?:saturday|sat)": "next_saturday",
    r"next\s*(?:sunday|sun)": "next_sunday",
    r"agla\s*(?:somvar|monday)": "next_monday",
    r"agla\s*(?:mangalvar|tuesday)": "next_tuesday",
    r"agla\s*(?:budhvar|wednesday)": "next_wednesday",
    r"agla\s*(?:guruvar|thursday)": "next_thursday",
    r"agla\s*(?:shukravar|friday)": "next_friday",
    r"agla\s*(?:shanivar|saturday)": "next_saturday",
    r"agla\s*(?:ravivar|sunday)": "next_sunday",
}

WEEKDAY_MAP = {
    "next_monday": 0, "next_tuesday": 1, "next_wednesday": 2,
    "next_thursday": 3, "next_friday": 4, "next_saturday": 5,
    "next_sunday": 6,
}


def might_be_absence(text: str) -> bool:
    """Quick keyword check to see if a message indicates absence."""
    text_lower = text.lower()
    all_keywords = ABSENCE_KEYWORDS_HI + ABSENCE_KEYWORDS_EN
    return any(kw in text_lower for kw in all_keywords)


def parse_absence_date(text: str) -> date:
    """
    Extract the intended absence date from message text.
    Returns today if no future date indicator is found.
    """
    text_lower = text.lower()
    today = date.today()

    for pattern, value in FUTURE_DATE_PATTERNS_HI.items():
        match = re.search(pattern, text_lower)
        if not match:
            continue

        if isinstance(value, int):
            return today + timedelta(days=value)

        if value is None and match.groups():
            days_ahead = int(match.group(1))
            return today + timedelta(days=min(days_ahead, 30))

        if isinstance(value, str) and value in WEEKDAY_MAP:
            target_weekday = WEEKDAY_MAP[value]
            days_ahead = (target_weekday - today.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            return today + timedelta(days=days_ahead)

    return today


async def record_absence(
    parent: Parent,
    reason: str | None,
    db: AsyncSession,
    absence_date: date | None = None,
) -> HousehelpAbsence:
    """Create an absence record for a househelp member."""
    today = date.today()
    target_date = absence_date or today
    is_advance = target_date > today

    result = await db.execute(
        select(HousehelpAbsence).where(
            and_(
                HousehelpAbsence.parent_id == parent.id,
                HousehelpAbsence.date == target_date,
            )
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        if reason:
            existing.reason = reason
        return existing

    absence = HousehelpAbsence(
        family_id=parent.family_id,
        parent_id=parent.id,
        date=target_date,
        reason=reason,
        is_advance_notice=is_advance,
        advance_notice_date=today if is_advance else None,
        slot_check_active=is_advance,
    )
    db.add(absence)
    await db.flush()
    return absence


async def create_absence_from_client(
    parent: Parent,
    db: AsyncSession,
    *,
    absence_date: date,
    end_date: date | None = None,
    affected_meals: list[str] | None = None,
    reason: str | None = None,
) -> HousehelpAbsence:
    """Client-driven absence creation (mobile app `POST /absences`).

    Distinct from `record_absence`:
      - No WhatsApp message back to the cook (the user is in-app, not
        responding to a cook's text).
      - No slot-check polling kick-off (the household marked it; they
        already know their plan).
      - `sync_source = "mobile_app"` so we can audit origin in incidents.

    Idempotent on (parent_id, absence_date) — a client retry that
    re-POSTs the same absence merges richer fields onto the existing
    row instead of creating a duplicate.
    """
    result = await db.execute(
        select(HousehelpAbsence).where(
            and_(
                HousehelpAbsence.parent_id == parent.id,
                HousehelpAbsence.date == absence_date,
            )
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        if end_date is not None:
            existing.end_date = end_date
        if affected_meals is not None:
            existing.affected_meals = affected_meals
        if reason and not existing.reason:
            existing.reason = reason
        await db.flush()
        return existing

    today = date.today()
    is_advance = absence_date > today
    absence = HousehelpAbsence(
        family_id=parent.family_id,
        parent_id=parent.id,
        date=absence_date,
        end_date=end_date,
        affected_meals=affected_meals,
        reason=reason,
        is_advance_notice=is_advance,
        advance_notice_date=today if is_advance else None,
        sync_source="mobile_app",
    )
    db.add(absence)
    await db.flush()
    return absence


async def update_absence_fallback(
    absence_id: uuid.UUID,
    db: AsyncSession,
    *,
    fallback_chosen: str | None,
    fallback_details: str | None,
) -> HousehelpAbsence | None:
    """Set or clear the household's fallback choice for an absence.

    Passing `fallback_chosen=None` clears both the chosen value and any
    details (mirrors the frontend's `chooseFallback(id, null)` un-resolve
    flow that sends the absence back to "action needed").
    """
    result = await db.execute(
        select(HousehelpAbsence).where(HousehelpAbsence.id == absence_id)
    )
    absence = result.scalar_one_or_none()
    if not absence:
        return None
    absence.fallback_chosen = fallback_chosen
    absence.fallback_details = fallback_details if fallback_chosen else None
    await db.flush()
    return absence


async def get_absences(
    family_id: uuid.UUID,
    db: AsyncSession,
    since_days: int = 30,
) -> list[HousehelpAbsence]:
    since = date.today() - __import__("datetime").timedelta(days=since_days)
    result = await db.execute(
        select(HousehelpAbsence)
        .where(
            and_(
                HousehelpAbsence.family_id == family_id,
                HousehelpAbsence.date >= since,
            )
        )
        .order_by(HousehelpAbsence.date.desc())
    )
    return list(result.scalars().all())


def build_replacement_card(parent: Parent, absence: HousehelpAbsence) -> dict:
    """Build a structured card with replacement options for the approver UI."""
    role = parent.role or "other"
    options = get_replacement_options(role)

    return {
        "absence_id": str(absence.id),
        "househelp_name": parent.name,
        "role": role,
        "date": absence.date.isoformat(),
        "reason": absence.reason,
        "replacement_options": options,
    }


async def book_replacement(
    absence_id: uuid.UUID,
    platform_id: str,
    db: AsyncSession,
) -> HousehelpAbsence | None:
    """Mark an absence as having a replacement booked."""
    result = await db.execute(
        select(HousehelpAbsence).where(HousehelpAbsence.id == absence_id)
    )
    absence = result.scalar_one_or_none()
    if not absence:
        return None

    options = get_replacement_options("cook")
    deep_link = None
    for opt in options:
        if opt["platform_id"] == platform_id:
            deep_link = opt["deep_link"]
            break

    if not deep_link:
        from app.services.platforms import get_replacement_options as get_opts
        for role in ["cook", "maid", "driver", "dog_walker"]:
            for opt in get_opts(role):
                if opt["platform_id"] == platform_id:
                    deep_link = opt["deep_link"]
                    break
            if deep_link:
                break

    absence.replacement_booked = True
    absence.replacement_platform = platform_id
    absence.replacement_deep_link = deep_link
    await db.flush()
    return absence
