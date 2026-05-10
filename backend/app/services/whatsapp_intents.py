"""
WhatsApp intent classifier — backend mirror of bimi/app/lib/whatsapp-intents.ts.

The frontend defines the *contract* (the typed `InboundIntent` union and
the `INTENT_DISPATCH` map). This module is the backend *implementation*
of that contract: takes inbound text (or transcribed voice) plus sender
metadata, returns one of the typed intents, and routes it to the right
service handler.

Status: skeleton. The classifier here uses regex/keyword matching — a
deliberate v0. The plan is to swap in OpenAI structured-output
classification once we have ~200 labelled real-world cook + member
messages from the pilot. Until then, the rule-based v0 covers the
~80% of canonical phrasings (atta khatam, kal nahi aaungi, dinner:
rajma, etc.) and falls through to `unknown` for anything else, which
the kitchen lead can triage from the cook-actions hero.

Usage from the WhatsApp webhook router:

    from app.services.whatsapp_intents import classify_inbound, dispatch

    intent = await classify_inbound(text=msg.text, from_phone=phone, db=db)
    await dispatch(intent, db=db)
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal, TypedDict

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ── Intent type union ─────────────────────────────────────────────────
# Mirrors `InboundIntent` in bimi/app/lib/whatsapp-intents.ts. Kept in
# sync manually; future work could codegen one from the other.

IntentKind = Literal[
    # Member intents
    "vote_meal",
    "vote_emoji_react",
    "decide_dinner_now",
    "skip_meal",
    "out_for_meal",
    "add_to_grocery",
    "ran_out",
    "rate_meal",
    "give_cook_off",
    "ack_cook_action",
    # Cook intents
    "cook_low_stock",
    "cook_absence",
    "cook_running_late",
    "cook_meal_query",
    "cook_prep_failed",
    # Fallback
    "unknown",
]


@dataclass
class InboundIntent:
    """Typed intent extracted from a WhatsApp message."""

    kind: IntentKind
    raw_text: str
    from_phone: str
    is_from_cook: bool
    family_id: uuid.UUID | None
    member_id: uuid.UUID | None
    received_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    # Extra structured data per kind. Kept as a free dict to avoid a
    # combinatorial explosion of dataclasses; consumers cast as needed.
    payload: dict[str, Any] = field(default_factory=dict)


# ── Classifier ────────────────────────────────────────────────────────

# Keyword sets — Hindi (Romanised) and English. Keep these tight; broad
# matches cause misclassification at scale.
_LOW_STOCK_TOKENS = (
    "khatam", "khatm", "kham", "kuch nahi", "running low", "out of",
    "low on", "kam ho gay", "khali", "almost over",
)
_ABSENCE_TOKENS = (
    "nahi aa rahi", "nahi aaungi", "nahi aa rahaa", "nahi aaungaa",
    "off rahungi", "kal off", "won't come", "wont come", "off tomorrow",
    "off today", "off kal", "off aaj",
)
_LATE_TOKENS = (
    "late", "der ho", "deri", "thodi der", "running late", "aane mein",
)
_RATING_TOKENS = (
    ("loved", 5), ("amazing", 5), ("excellent", 5), ("super", 5),
    ("acha tha", 4), ("good", 4), ("nice", 4),
    ("ok", 3), ("theek", 3), ("decent", 3),
    ("not great", 2), ("bekar", 2),
    ("bad", 1), ("worst", 1), ("hated", 1),
)
_OUT_TOKENS = (
    "out tonight", "out for dinner", "skip me", "won't eat",
    "wont eat", "not eating", "ghar nahi hu", "bahar hu",
)
_GROCERY_VERBS = (
    "add", "order", "chahiye", "mangwa", "buy", "le aana",
)
_VOTE_PREFIX = ("dinner:", "lunch:", "breakfast:", "tonight:", "tomorrow:")
_GIVE_OFF_TOKENS = (
    "give didi off", "didi off", "cook off",
    "give cook a day off", "cook ko off",
)


def _detect_rating(text: str) -> int | None:
    lower = text.lower()
    # Star-emoji parsing: "★★★★" = 4
    stars = lower.count("\u2605")
    if 1 <= stars <= 5:
        return stars
    # Word-based fallback
    for token, rating in _RATING_TOKENS:
        if token in lower:
            return rating
    return None


def _detect_meal_type(text: str) -> str | None:
    lower = text.lower()
    if "dinner" in lower or "raat" in lower:
        return "dinner"
    if "lunch" in lower or "dopahar" in lower:
        return "lunch"
    if "breakfast" in lower or "subah" in lower:
        return "breakfast"
    return None


def _detect_when(text: str) -> str:
    """Returns 'today' or 'tomorrow' based on the message; defaults to today."""
    lower = text.lower()
    if "kal" in lower or "tomorrow" in lower:
        return "tomorrow"
    return "today"


def _to_iso_date(when: Literal["today", "tomorrow"]) -> str:
    today = date.today()
    if when == "tomorrow":
        return (today + timedelta(days=1)).isoformat()
    return today.isoformat()


# ── Lookup helpers ────────────────────────────────────────────────────
# These query the DB to resolve sender phone → (member_id, family_id,
# is_from_cook). Stubbed out so the function signature is stable; real
# implementation lives in cook_context.lookup_shared_cook + family
# lookups already in the codebase.


class SenderResolution(TypedDict):
    family_id: uuid.UUID | None
    member_id: uuid.UUID | None
    is_from_cook: bool


async def resolve_sender(phone: str, db: AsyncSession) -> SenderResolution:
    """Resolve a phone number to family/member context.

    Implementation note: the existing webhook router already does this
    via `cook_context.lookup_shared_cook` (cook side) and Parent lookups
    (member side). Wire this through during the integration step. For
    now, return all-None so the classifier still works in unit tests.
    """
    # TODO: wire to existing helpers in app.services.cook_context.
    return SenderResolution(family_id=None, member_id=None, is_from_cook=False)


# ── Main classifier ───────────────────────────────────────────────────

async def classify_inbound(
    text: str,
    from_phone: str,
    db: AsyncSession,
) -> InboundIntent:
    """Classify an inbound WhatsApp message into a typed InboundIntent.

    The function tries a sequence of cheap, ordered checks (most specific
    first). Anything unmatched falls through to `unknown` — the kitchen
    lead sees these in the cook-actions hero as 'Note from cook' rows
    with the verbatim text.
    """
    sender = await resolve_sender(from_phone, db)
    base_kwargs = {
        "raw_text": text,
        "from_phone": from_phone,
        "family_id": sender["family_id"],
        "member_id": sender["member_id"],
        "is_from_cook": sender["is_from_cook"],
    }
    lower = text.lower().strip()

    # Empty / whitespace-only
    if not lower:
        return InboundIntent(kind="unknown", **base_kwargs)

    # ── Cook-side intents (only fire if sender is a cook) ───────────
    if sender["is_from_cook"]:
        if any(t in lower for t in _ABSENCE_TOKENS):
            return InboundIntent(
                kind="cook_absence",
                payload={"date": _to_iso_date(_detect_when(text)), "reason": text},
                **base_kwargs,
            )
        if any(t in lower for t in _LATE_TOKENS):
            mins_match = re.search(r"(\d{1,3})\s*(?:min|minute)", lower)
            mins = int(mins_match.group(1)) if mins_match else 30
            return InboundIntent(
                kind="cook_running_late",
                payload={"minutes": mins},
                **base_kwargs,
            )
        if any(t in lower for t in _LOW_STOCK_TOKENS):
            severity: Literal["low", "out"] = "out" if "khatam" in lower or "out of" in lower else "low"
            return InboundIntent(
                kind="cook_low_stock",
                payload={"item_name": text, "severity": severity},
                **base_kwargs,
            )
        if "?" in text or lower.startswith(("kya ", "what ")):
            return InboundIntent(
                kind="cook_meal_query",
                payload={"question": text},
                **base_kwargs,
            )

    # ── Member-side intents ─────────────────────────────────────────

    # Rating: "loved it", star count, etc — match BEFORE generic
    # vote/meal-name parse so "rajma was excellent" doesn't classify
    # as decide_dinner_now.
    rating = _detect_rating(text)
    if rating is not None and _detect_meal_type(text):
        meal_type = _detect_meal_type(text) or "dinner"
        return InboundIntent(
            kind="rate_meal",
            payload={
                "date": _to_iso_date(_detect_when(text)),
                "meal_type": meal_type,
                "rating": rating,
            },
            **base_kwargs,
        )

    # Skip / out-tonight
    if any(t in lower for t in _OUT_TOKENS):
        return InboundIntent(
            kind="out_for_meal",
            payload={
                "date": _to_iso_date(_detect_when(text)),
                "meal_type": _detect_meal_type(text) or "dinner",
            },
            **base_kwargs,
        )

    # Give cook off
    if any(t in lower for t in _GIVE_OFF_TOKENS):
        return InboundIntent(
            kind="give_cook_off",
            payload={"date": _to_iso_date(_detect_when(text))},
            **base_kwargs,
        )

    # Direct dinner decision: "dinner: rajma chawal"
    for prefix in _VOTE_PREFIX:
        if lower.startswith(prefix):
            dish = text[len(prefix):].strip()
            return InboundIntent(
                kind="decide_dinner_now",
                payload={"dish_name": dish},
                **base_kwargs,
            )

    # Grocery add intent — verb + noun
    if any(verb in lower for verb in _GROCERY_VERBS):
        return InboundIntent(
            kind="add_to_grocery",
            payload={"raw": text},
            **base_kwargs,
        )

    # Ran out (member side, eg "doodh khatam")
    if any(t in lower for t in _LOW_STOCK_TOKENS):
        return InboundIntent(
            kind="ran_out",
            payload={"item_name": text},
            **base_kwargs,
        )

    # Fallback — surface to lead via cook-actions hero
    return InboundIntent(kind="unknown", **base_kwargs)


# ── Dispatcher ────────────────────────────────────────────────────────

async def dispatch(intent: InboundIntent, db: AsyncSession) -> dict[str, Any]:
    """Route a classified intent to the appropriate service handler.

    Returns a result dict the webhook can echo back to the sender
    ("Got it. Adding 1L milk to tomorrow's order.").

    Status: skeleton. Each branch logs + returns a placeholder result.
    Real handler wiring lives in the existing service modules
    (meal_engine, inventory, absence, etc) — the contract here is that
    every InboundIntent variant has exactly one home.
    """
    handler_map: dict[IntentKind, str] = {
        "vote_meal": "app.services.meal_engine.submit_vote",
        "vote_emoji_react": "app.services.meal_engine.submit_vote_via_poll",
        "decide_dinner_now": "app.services.meal_engine.finalize_plan_directly",
        "skip_meal": "app.services.meal_engine.skip_meal",
        "out_for_meal": "app.services.meal_engine.mark_member_absent",
        "add_to_grocery": "app.services.intent.extract_intent",
        "ran_out": "app.services.inventory.mark_depleted",
        "rate_meal": "app.services.meal_engine.rate_meal",
        "give_cook_off": "app.services.absence.add_absence",
        "ack_cook_action": "app.services.cook_context.resolve_action",
        "cook_low_stock": "app.services.inventory.mark_low_stock",
        "cook_absence": "app.services.absence.add_absence",
        "cook_running_late": "app.services.cook_context.add_late_message",
        "cook_meal_query": "app.services.cook_context.add_meal_query",
        "cook_prep_failed": "app.services.cook_context.add_prep_failed",
        "unknown": "app.services.cook_context.add_verbatim_for_triage",
    }

    handler_path = handler_map[intent.kind]
    logger.info(
        "WhatsApp intent dispatch — kind=%s handler=%s phone=%s family=%s",
        intent.kind,
        handler_path,
        intent.from_phone,
        intent.family_id,
    )

    # TODO: actually import and call each handler. For now, this is a
    # contract-only stub — every intent has a single declared dispatch
    # target so future work has a clear hook list.
    return {
        "status": "received",
        "kind": intent.kind,
        "handler": handler_path,
        "echo": _confirmation_echo(intent),
    }


def _confirmation_echo(intent: InboundIntent) -> str:
    """The reply Bimi sends back to the sender. Hindi for cook side,
    English for member side, single short line."""

    if intent.kind == "cook_absence":
        return "Bimi sun li, didi. Ghar wale ko bata diya jaayega."
    if intent.kind == "cook_running_late":
        mins = intent.payload.get("minutes", 30)
        return f"Bimi sun li. {mins} minute late ka message bhej diya."
    if intent.kind == "cook_low_stock":
        return "Bimi sun li. Ghar wale ko bata diya jaayega."
    if intent.kind == "add_to_grocery":
        return "Adding to next order. I'll confirm the total in a minute."
    if intent.kind == "decide_dinner_now":
        return f"Got it — {intent.payload.get('dish_name', 'dinner')} it is. Briefing didi."
    if intent.kind == "give_cook_off":
        return "Done. I'll let didi know and figure out the day's plan."
    if intent.kind == "rate_meal":
        return "Thanks for the feedback — Bimi will remember this."
    if intent.kind == "skip_meal" or intent.kind == "out_for_meal":
        return "Noted. I'll adjust portions for tonight."
    if intent.kind == "ran_out":
        return "Adding to the next order."
    if intent.kind == "unknown":
        return "Got your message — Bimi will pass it along."
    return "Got it."


# ── Cook prompts ─────────────────────────────────────────────────────
# Mirrors COOK_PROMPT_FOR_ACTION in the frontend. Used when Bimi is the
# initiator of a cook conversation (e.g., the morning brief or a poll).

COOK_PROMPT_FOR_ACTION: dict[str, str] = {
    "supply_request": "Kya order karu? Reply with item names ya 'ok' agar standard list theek hai.",
    "meal_query": "Aaj kya banaye? Reply with dish name.",
    "low_stock": "Kya kam ho gaya? Item name bata do.",
    "absence": "Kal aana hai ya nahi? Reply 'aaungi' / 'nahi aaungi'.",
    "prep_note": "Note saved. No reply needed.",
    "prep_failed": "Backup banayein? Reply yes / no — Bimi alternative bata degi.",
}
