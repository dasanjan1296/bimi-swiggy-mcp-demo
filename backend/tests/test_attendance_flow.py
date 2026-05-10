"""Daily attendance check-in + partial-day deviation flow.

Slice 2 of the WhatsApp coordination plan. Covers:
  - Time parser: "2 baje" / "10:30 am" / "saade teen" / etc.
  - Late-arrival button flow: stash → cook replies with ETA → record + notify
  - Early-leave proactive flow ("doctor jaana hai 2 baje")
  - Late-arrival proactive flow ("late hoongi 10 baje")
  - Notify-parent payload uses deviation type + time, no replacement booking
  - Morning check-in card: skipped when an absence row already exists
"""
from __future__ import annotations

from datetime import UTC, date, datetime, time

import pytest

from app.models.family import Parent
from app.models.meal import HousehelpAbsence
from app.services.attendance import (
    _reset_pending_eta_for_tests,
    might_be_early_leave,
    might_be_late_arrival,
    needs_morning_checkin,
    parse_arrival_or_leave_time,
    pop_pending_eta,
    record_early_leave,
    record_late_arrival,
    send_morning_checkin,
    stash_pending_eta,
)


@pytest.fixture(autouse=True)
def _clear_pending_eta():
    _reset_pending_eta_for_tests()
    yield
    _reset_pending_eta_for_tests()


async def _make_cook(db, family_id, *, phone="+919900222222", name="Geeta"):
    p = Parent(
        family_id=family_id,
        name=name,
        phone=phone,
        whatsapp_id=phone.lstrip("+"),
        role="cook",
        language="hi",
    )
    db.add(p)
    await db.flush()
    return p


# ---------------------------------------------------------------------------
# Time parser — pure unit tests
# ---------------------------------------------------------------------------


def test_parse_time_baje_default_pm_for_early_leave():
    # "2 baje nikal jaungi" — default PM since 2 AM is implausible
    assert parse_arrival_or_leave_time("2 baje nikal jaungi", default_pm=True) == time(14, 0)


def test_parse_time_baje_default_am_for_late_arrival():
    # "10 baje aaungi" with default_pm=False resolves to 10 AM
    assert parse_arrival_or_leave_time("10 baje aaungi", default_pm=False) == time(10, 0)


def test_parse_time_explicit_am():
    assert parse_arrival_or_leave_time("9:30 am tak aaungi", default_pm=True) == time(9, 30)


def test_parse_time_explicit_pm():
    assert parse_arrival_or_leave_time("5 pm tak nikal jaungi", default_pm=True) == time(17, 0)


def test_parse_time_subah_marker():
    assert parse_arrival_or_leave_time("subah 9 baje aaungi", default_pm=True) == time(9, 0)


def test_parse_time_shaam_marker():
    assert parse_arrival_or_leave_time("shaam 6 baje", default_pm=True) == time(18, 0)


def test_parse_time_saade_teen():
    # "saade teen" = 3:30
    assert parse_arrival_or_leave_time("saade teen baje", default_pm=True) == time(15, 30)


def test_parse_time_unparseable_returns_none():
    assert parse_arrival_or_leave_time("kuch toh banana hai", default_pm=True) is None


def test_might_be_early_leave_detects_common_phrases():
    assert might_be_early_leave("aaj jaldi jaana hai") is True
    assert might_be_early_leave("doctor jaungi 3 baje") is True
    assert might_be_early_leave("aaj half day chahiye") is True
    assert might_be_early_leave("aaj khana ban gaya") is False


def test_might_be_late_arrival_detects_common_phrases():
    assert might_be_late_arrival("late hoongi aaj") is True
    assert might_be_late_arrival("der ho jayegi") is True
    assert might_be_late_arrival("aaj on time hoon") is False


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_late_arrival_creates_row(db, seed_family):
    cook = await _make_cook(db, seed_family["family_id"])
    row = await record_late_arrival(cook, time(10, 0), db, reason="bus miss ho gayi")

    assert row.late_arrival_time == time(10, 0)
    assert row.early_leave_time is None
    assert row.replacement_booked is False
    assert row.date == date.today()


@pytest.mark.asyncio
async def test_record_early_leave_on_same_day_updates_existing_row(db, seed_family):
    cook = await _make_cook(db, seed_family["family_id"])
    await record_late_arrival(cook, time(10, 0), db)
    row = await record_early_leave(cook, time(15, 0), db)

    # Same row, both fields set — the cook came late AND is leaving early
    assert row.late_arrival_time == time(10, 0)
    assert row.early_leave_time == time(15, 0)


# ---------------------------------------------------------------------------
# Pending ETA stash + pop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pending_eta_stash_and_pop(db, seed_family):
    cook = await _make_cook(db, seed_family["family_id"])
    await stash_pending_eta(cook.whatsapp_id, str(cook.id))

    pending = await pop_pending_eta(cook.whatsapp_id)
    assert pending is not None
    assert pending.parent_id == str(cook.id)

    # Second pop returns None — the marker is consumed
    assert await pop_pending_eta(cook.whatsapp_id) is None


# ---------------------------------------------------------------------------
# Morning check-in
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_needs_morning_checkin_true_on_clean_day(db, seed_family):
    cook = await _make_cook(db, seed_family["family_id"])
    assert await needs_morning_checkin(cook, db) is True


@pytest.mark.asyncio
async def test_needs_morning_checkin_false_when_already_declared(db, seed_family):
    cook = await _make_cook(db, seed_family["family_id"])
    db.add(HousehelpAbsence(
        family_id=cook.family_id,
        parent_id=cook.id,
        date=date.today(),
        late_arrival_time=time(10, 0),
    ))
    await db.flush()
    assert await needs_morning_checkin(cook, db) is False


@pytest.mark.asyncio
async def test_send_morning_checkin_sends_three_button_card(
    db, seed_family, fake_whatsapp,
):
    cook = await _make_cook(db, seed_family["family_id"])
    fake_whatsapp.reset()

    await send_morning_checkin(cook)

    sent = fake_whatsapp.messages_to(cook.whatsapp_id)
    assert len(sent) == 1
    payload = sent[0].payload
    assert payload["type"] == "interactive"
    buttons = payload["interactive"]["action"]["buttons"]
    button_ids = [b["reply"]["id"] for b in buttons]
    assert button_ids == [
        f"attend_yes_{cook.id}",
        f"attend_no_{cook.id}",
        f"attend_late_{cook.id}",
    ]
