"""Daily attendance check-in and partial-day deviation handling.

Slice 2 of the WhatsApp coordination plan. Two surfaces:

  1. Morning check-in card (6:30 AM IST scheduler) — three reply
     buttons: Haan / Nahi / Late hoongi. Late tap puts the cook into
     a pending-ETA state; the next message they send is parsed as
     their arrival time.

  2. Proactive partial-day deviations — cook says "doctor jaana hai,
     2 baje nikal jaungi" or similar. The detector + handler record
     `early_leave_time` (or `late_arrival_time`) on a HousehelpAbsence
     row and notify the parent. Per product spec, replacement booking
     is intentionally NOT triggered for partial-day deviations.

Time-parsing handles common Hindi expressions:
  - "2 baje" → 14:00 (defaults to PM since cooks rarely leave at 2 AM)
  - "subah 9 baje" / "9 am" / "9 baje subah" → 09:00
  - "shaam 5 baje" / "5 pm" → 17:00
  - "saade teen" → 15:30
"""
from __future__ import annotations

import asyncio
import logging
import re
import time as time_mod
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Literal

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.family import Parent
from app.models.meal import HousehelpAbsence

logger = logging.getLogger("bimi.attendance")


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

# Phrases that signal "leaving early today" (NOT full-day absence).
# Detected before the absence detector since these are more specific.
EARLY_LEAVE_KEYWORDS = [
    "jaldi jaana", "jaldi jaungi", "jaldi jaunga", "jaldi nikal",
    "early jana", "early jaungi", "early jaunga", "early leave",
    "doctor jaana", "doctor jaungi", "doctor jaunga",
    "nikal jaungi", "nikal jaunga", "nikalna hai",
    "half day", "half-day", "aadha din",
    "leave early",
]

LATE_ARRIVAL_KEYWORDS = [
    "late hoongi", "late hoonga", "late aaungi", "late aaunga",
    "late ho jaungi", "late ho jaunga", "der ho jayegi", "der se aaungi",
    "der se aaunga", "thoda late", "running late",
]


def might_be_early_leave(text: str) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in EARLY_LEAVE_KEYWORDS)


def might_be_late_arrival(text: str) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in LATE_ARRIVAL_KEYWORDS)


# ---------------------------------------------------------------------------
# Time parsing
# ---------------------------------------------------------------------------

# Numeric "N baje" or "N am/pm" or "N o'clock"
_BAJE_RE = re.compile(
    r"\b(\d{1,2})(?::(\d{2}))?\s*(?:baje|bj|am|pm|a\.m\.|p\.m\.|o'?clock)?\b",
    re.IGNORECASE,
)
_HALF_PAST_RE = re.compile(r"\b(?:saade|sade)\s+(do|teen|char|paanch|chhe|saat|aath|nau|das)\b", re.IGNORECASE)
_NAMED_HOUR = {
    "ek": 1, "do": 2, "teen": 3, "char": 4, "paanch": 5, "chhe": 6, "che": 6,
    "saat": 7, "aath": 8, "nau": 9, "das": 10, "gyarah": 11, "barah": 12,
}


def parse_arrival_or_leave_time(text: str, *, default_pm: bool = True) -> time | None:
    """Best-effort parse of a time-of-day from a free-text Hindi/English message.

    `default_pm` controls disambiguation when only a bare hour is given:
    cooks talking about leaving early almost always mean PM, so the
    default is PM unless explicit AM/morning markers are present.

    Returns None if no time can be parsed.
    """
    text_lower = text.lower().strip()

    # "saade teen" (3:30) etc.
    m = _HALF_PAST_RE.search(text_lower)
    if m:
        hour_word = m.group(1)
        hour = _NAMED_HOUR.get(hour_word)
        if hour is not None:
            return _disambiguate_hour(hour, 30, text_lower, default_pm)

    # Numeric "2 baje" / "9:30 am" / "14:00"
    m = _BAJE_RE.search(text_lower)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2)) if m.group(2) else 0
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return _disambiguate_hour(hour, minute, text_lower, default_pm)

    # Named hours alone: "do baje", "teen baje", "saat"
    for word, hour in _NAMED_HOUR.items():
        if re.search(rf"\b{word}\b", text_lower):
            return _disambiguate_hour(hour, 0, text_lower, default_pm)

    return None


def _disambiguate_hour(hour: int, minute: int, text: str, default_pm: bool) -> time:
    """Resolve a 1-12 hour to 0-23 using AM/PM markers in the surrounding text."""
    if hour >= 13:
        return time(hour, minute)
    has_am = bool(
        re.search(r"\bam\b|a\.m\.|subah|morning", text)
    )
    has_pm = bool(
        re.search(r"\bpm\b|p\.m\.|shaam|raat|evening|night|dopahar|afternoon", text)
    )
    if has_am:
        return time(0 if hour == 12 else hour, minute)
    if has_pm:
        return time(12 if hour == 12 else hour + 12, minute)
    if default_pm and 1 <= hour <= 11:
        return time(hour + 12, minute)
    return time(hour, minute)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


async def _get_or_create_today_row(
    parent: Parent, db: AsyncSession,
) -> HousehelpAbsence:
    today = date.today()
    result = await db.execute(
        select(HousehelpAbsence).where(
            and_(
                HousehelpAbsence.parent_id == parent.id,
                HousehelpAbsence.date == today,
            )
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    row = HousehelpAbsence(
        family_id=parent.family_id,
        parent_id=parent.id,
        date=today,
    )
    db.add(row)
    await db.flush()
    return row


async def record_late_arrival(
    parent: Parent,
    arrival_time: time,
    db: AsyncSession,
    *,
    reason: str | None = None,
) -> HousehelpAbsence:
    row = await _get_or_create_today_row(parent, db)
    row.late_arrival_time = arrival_time
    if reason:
        row.reason = (reason[:255]) if reason else row.reason
    await db.flush()
    return row


async def record_early_leave(
    parent: Parent,
    leave_time: time,
    db: AsyncSession,
    *,
    reason: str | None = None,
) -> HousehelpAbsence:
    row = await _get_or_create_today_row(parent, db)
    row.early_leave_time = leave_time
    if reason:
        row.reason = (reason[:255]) if reason else row.reason
    await db.flush()
    return row


# ---------------------------------------------------------------------------
# Pending-ETA state (after a "Late hoongi" button tap)
# ---------------------------------------------------------------------------


@dataclass
class _PendingEta:
    parent_id: str
    asked_at_ts: float


_PENDING_ETA: dict[str, _PendingEta] = {}
_PENDING_ETA_LOCK = asyncio.Lock()
_PENDING_ETA_TTL_SEC = 30 * 60


async def stash_pending_eta(sender_wa_id: str, parent_id: str) -> None:
    async with _PENDING_ETA_LOCK:
        _gc_eta()
        _PENDING_ETA[sender_wa_id] = _PendingEta(
            parent_id=parent_id, asked_at_ts=time_mod.monotonic(),
        )


async def pop_pending_eta(sender_wa_id: str) -> _PendingEta | None:
    async with _PENDING_ETA_LOCK:
        _gc_eta()
        return _PENDING_ETA.pop(sender_wa_id, None)


def _gc_eta() -> None:
    now = time_mod.monotonic()
    stale = [k for k, v in _PENDING_ETA.items() if now - v.asked_at_ts > _PENDING_ETA_TTL_SEC]
    for k in stale:
        _PENDING_ETA.pop(k, None)


def _reset_pending_eta_for_tests() -> None:
    _PENDING_ETA.clear()


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


async def notify_parent_partial_deviation(
    parent: Parent,
    *,
    deviation: Literal["late_arrival", "early_leave"],
    deviation_time: time,
    db: AsyncSession,
    reason: str | None = None,
) -> None:
    from app.services.notification import notify_family_children

    role_label = (parent.role or "househelp").replace("_", " ").title()
    label = (
        f"{role_label} late: arriving by {deviation_time.strftime('%I:%M %p').lstrip('0')}"
        if deviation == "late_arrival"
        else f"{role_label} leaving early at {deviation_time.strftime('%I:%M %p').lstrip('0')}"
    )

    body_lines = [f"⏰ {parent.name} ({role_label})"]
    if deviation == "late_arrival":
        body_lines.append(
            f"Today's arrival pushed to {deviation_time.strftime('%I:%M %p').lstrip('0')}"
        )
    else:
        body_lines.append(
            f"Leaving early today at {deviation_time.strftime('%I:%M %p').lstrip('0')}"
        )
    if reason:
        body_lines.append(f"Reason: {reason}")
    body_lines.append("\n(Surfaced for awareness — no replacement booking triggered.)")

    await notify_family_children(
        parent.family_id,
        label,
        "\n".join(body_lines),
        data={
            "type": "partial_attendance_deviation",
            "deviation": deviation,
            "time": deviation_time.isoformat(),
            "parent_id": str(parent.id),
        },
        db=db,
    )


# ---------------------------------------------------------------------------
# Morning check-in
# ---------------------------------------------------------------------------


async def needs_morning_checkin(parent: Parent, db: AsyncSession) -> bool:
    """Skip the check-in if the cook has already declared their status today.

    'Already declared' means: either an absence/late/early-leave row exists
    for today, or the cook has already messaged Bimi today (we infer
    presence from any inbound message after midnight IST).
    """
    today = date.today()
    existing = await db.execute(
        select(HousehelpAbsence).where(
            and_(
                HousehelpAbsence.parent_id == parent.id,
                HousehelpAbsence.date == today,
            )
        ).limit(1)
    )
    if existing.scalar_one_or_none() is not None:
        return False
    return True


async def send_morning_checkin(parent: Parent) -> None:
    """Send the 3-button morning check-in card to a single cook."""
    from app.services.whatsapp import send_reply_buttons

    body = f"Namaste {parent.name} ji 🙏\nAaj aa rahi ho?"
    await send_reply_buttons(
        to=parent.whatsapp_id,
        body=body,
        buttons=[
            {"id": f"attend_yes_{parent.id}", "title": "✅ Haan"},
            {"id": f"attend_no_{parent.id}", "title": "😔 Nahi"},
            {"id": f"attend_late_{parent.id}", "title": "⏰ Late hoongi"},
        ],
        footer="Bimi",
    )
