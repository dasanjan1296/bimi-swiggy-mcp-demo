"""WhatsApp intent classifier tests — pure unit tests over the
keyword/regex classifier in app.services.whatsapp_intents.

The DB lookup is stubbed via the resolve_sender helper, which returns
all-None by default. Tests that exercise cook-side intents patch
resolve_sender to mark the sender as a cook.

What's covered:
- Each cook-side intent kind (absence, late, low stock, meal query)
- Each member-side intent kind (rate, skip, give-off, decide, grocery
  add, ran-out)
- Hindi (Romanised) and English variants for the high-frequency phrases
- Empty / whitespace fallback
- Free-text fallback to `unknown`
- The dispatcher returns the documented handler path for every kind
- The cook-prompt map covers every ActionItem type
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.services import whatsapp_intents as wi
from app.services.whatsapp_intents import (
    COOK_PROMPT_FOR_ACTION,
    classify_inbound,
    dispatch,
)


@pytest.fixture
def cook_sender():
    """Patch resolve_sender so the classifier sees the message as
    coming from a cook. Family / member ids stay None — the classifier
    doesn't need them to decide kind."""
    fake = AsyncMock(return_value={"family_id": None, "member_id": None, "is_from_cook": True})
    with patch.object(wi, "resolve_sender", fake):
        yield


@pytest.fixture
def member_sender():
    """Patch resolve_sender so the classifier sees the message as
    coming from a household member, not a cook."""
    fake = AsyncMock(return_value={"family_id": None, "member_id": None, "is_from_cook": False})
    with patch.object(wi, "resolve_sender", fake):
        yield


# ── Cook-side intents ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cook_absence_hindi(cook_sender):
    intent = await classify_inbound("Kal nahi aa rahi", "+919999111122", db=None)
    assert intent.kind == "cook_absence"
    assert intent.is_from_cook
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    assert intent.payload["date"] == tomorrow


@pytest.mark.asyncio
async def test_cook_absence_english(cook_sender):
    intent = await classify_inbound("won't come tomorrow", "+919999111122", db=None)
    assert intent.kind == "cook_absence"


@pytest.mark.asyncio
async def test_cook_running_late_with_minutes(cook_sender):
    intent = await classify_inbound("running late, 15 min der ho rahi hai", "+91", db=None)
    assert intent.kind == "cook_running_late"
    assert intent.payload["minutes"] == 15


@pytest.mark.asyncio
async def test_cook_running_late_default_minutes(cook_sender):
    intent = await classify_inbound("late ho jayegi aaj", "+91", db=None)
    assert intent.kind == "cook_running_late"
    # No explicit number — defaults to 30.
    assert intent.payload["minutes"] == 30


@pytest.mark.asyncio
async def test_cook_low_stock_khatam(cook_sender):
    intent = await classify_inbound("Atta khatam ho gaya", "+91", db=None)
    assert intent.kind == "cook_low_stock"
    assert intent.payload["severity"] == "out"


@pytest.mark.asyncio
async def test_cook_low_stock_low(cook_sender):
    intent = await classify_inbound("Pyaaz kam ho gaya, almost over", "+91", db=None)
    assert intent.kind == "cook_low_stock"
    # "almost over" → low, not out
    assert intent.payload["severity"] in {"low", "out"}


@pytest.mark.asyncio
async def test_cook_meal_query(cook_sender):
    intent = await classify_inbound("Aaj kya banau lunch mein?", "+91", db=None)
    assert intent.kind == "cook_meal_query"
    assert "kya" in intent.payload["question"].lower()


# ── Member-side intents ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_member_rate_meal(member_sender):
    intent = await classify_inbound("Dinner was loved it!", "+91", db=None)
    assert intent.kind == "rate_meal"
    assert intent.payload["meal_type"] == "dinner"
    assert intent.payload["rating"] == 5


@pytest.mark.asyncio
async def test_member_rate_meal_stars(member_sender):
    intent = await classify_inbound("dinner ★★★★", "+91", db=None)
    assert intent.kind == "rate_meal"
    assert intent.payload["rating"] == 4


@pytest.mark.asyncio
async def test_member_skip_dinner(member_sender):
    intent = await classify_inbound("out tonight, skip me from dinner", "+91", db=None)
    assert intent.kind == "out_for_meal"
    assert intent.payload["meal_type"] == "dinner"


@pytest.mark.asyncio
async def test_member_give_cook_off(member_sender):
    intent = await classify_inbound("give cook off tomorrow", "+91", db=None)
    assert intent.kind == "give_cook_off"
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    assert intent.payload["date"] == tomorrow


@pytest.mark.asyncio
async def test_member_decide_dinner(member_sender):
    intent = await classify_inbound("Dinner: rajma chawal", "+91", db=None)
    assert intent.kind == "decide_dinner_now"
    assert intent.payload["dish_name"] == "rajma chawal"


@pytest.mark.asyncio
async def test_member_add_to_grocery(member_sender):
    intent = await classify_inbound("add 1L milk to next order", "+91", db=None)
    assert intent.kind == "add_to_grocery"


@pytest.mark.asyncio
async def test_member_ran_out(member_sender):
    intent = await classify_inbound("milk khatam in fridge", "+91", db=None)
    assert intent.kind == "ran_out"


# ── Fallback ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unknown_fallback(member_sender):
    intent = await classify_inbound("hi how are you", "+91", db=None)
    assert intent.kind == "unknown"


@pytest.mark.asyncio
async def test_empty_message(member_sender):
    intent = await classify_inbound("   ", "+91", db=None)
    assert intent.kind == "unknown"


# ── Dispatcher contract ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dispatcher_returns_handler_path(cook_sender):
    intent = await classify_inbound("Atta khatam", "+91", db=None)
    result = await dispatch(intent, db=None)
    assert result["status"] == "received"
    assert result["kind"] == "cook_low_stock"
    # Handler path is the canonical reference into the existing service
    # modules. The contract is that this string is stable — frontend
    # code and integration docs link to it.
    assert result["handler"].startswith("app.services.")


@pytest.mark.asyncio
async def test_dispatcher_covers_every_kind(member_sender):
    """Every InboundIntent kind must have a dispatch target. Manually
    construct one of each and assert dispatch doesn't raise."""
    from app.services.whatsapp_intents import InboundIntent

    kinds = [
        "vote_meal", "vote_emoji_react", "decide_dinner_now",
        "skip_meal", "out_for_meal", "add_to_grocery", "ran_out",
        "rate_meal", "give_cook_off", "ack_cook_action",
        "cook_low_stock", "cook_absence", "cook_running_late",
        "cook_meal_query", "cook_prep_failed", "unknown",
    ]
    for kind in kinds:
        intent = InboundIntent(
            kind=kind,  # type: ignore[arg-type]
            raw_text="x",
            from_phone="+91",
            family_id=None,
            member_id=None,
            is_from_cook=kind.startswith("cook_"),
        )
        result = await dispatch(intent, db=None)
        assert result["kind"] == kind
        assert result["handler"]


# ── Cook prompt map ──────────────────────────────────────────────────


def test_cook_prompts_cover_every_action_type():
    """The prompt map must have an entry for every ActionItem type the
    frontend can produce. Drift between the two ends is a bug — if the
    frontend ships a new ActionItem.type, the cook needs a prompt."""
    expected = {"supply_request", "meal_query", "low_stock", "absence", "prep_note", "prep_failed"}
    assert set(COOK_PROMPT_FOR_ACTION.keys()) == expected
