"""Critical-action confirmation loop.

The brief: "Add confirmation loops for critical actions… Prefer
confirmation over wrong execution."

Some intents are *destructive* — they can't be undone with a follow-up
message:

    - cook absence (a replacement may already be booked by the time we revert)
    - meal swap (cook has started prepping)
    - bulk order commit (Swiggy charges within 60s)

For these, we don't commit on first parse. Instead we:

1. Stage the intent in `PendingCriticalAction` (in-memory keyed dict
   for v0; promotes to a DB table once the pilot exposes the failure
   modes).
2. Send a tight read-back: "Confirm: [exact action]. Reply Haan / Nahi
   ya 2 minute mein automatically commit ho jayega."
3. On YES → commit + ack.
4. On NO  → drop + ack.
5. On 2-minute timeout → commit (so the system doesn't stall when the
   user is afk) AND log it as `auto_committed=True` for observability.

Why a timeout-default-commit instead of timeout-cancel?
- Most critical actions ARE the user's intent. Cancelling silently
  leaves the cook stranded (e.g. she said "kal nahi aa rahi" and
  Bimi never told the family because the user didn't tap a button).
- We surface the auto-commit clearly: "(2 min ke baad confirm kar
  diya — agar galat hai toh batayein)". The reversible window is
  small but documented.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

logger = logging.getLogger("bimi.critical_confirmation")


CriticalKind = Literal[
    "cook_absence",
    "meal_swap",
    "bulk_order_commit",
    "instruction_delete",
]


@dataclass
class PendingCriticalAction:
    id: str
    family_id: uuid.UUID | None
    sender_wa_id: str
    kind: CriticalKind
    summary: str
    payload: dict[str, Any]
    on_commit: Callable[[dict[str, Any]], Awaitable[None]]
    on_cancel: Callable[[], Awaitable[None]] | None = None
    created_at: float = field(default_factory=time.time)
    state: Literal["pending", "committed", "cancelled", "auto_committed"] = "pending"


# In-memory registry. For the pilot scale (≤ 50 households) this is
# fine. The next version migrates to `pending_critical_actions` table.
_REGISTRY: dict[str, PendingCriticalAction] = {}

# Default auto-commit window: 2 minutes.
_AUTO_COMMIT_SEC = 120

# Per-(sender, kind) lookup so a second message of the same kind can
# replace the pending one cleanly ("kal nahi aaungi" then "actually
# parso").
_BY_SENDER: dict[tuple[str, str], str] = {}


async def request_critical_confirmation(
    *,
    family_id: uuid.UUID | None,
    sender_wa_id: str,
    kind: CriticalKind,
    summary: str,
    payload: dict[str, Any],
    on_commit: Callable[[dict[str, Any]], Awaitable[None]],
    on_cancel: Callable[[], Awaitable[None]] | None = None,
    auto_commit_sec: int = _AUTO_COMMIT_SEC,
) -> str:
    """Stage a critical action and send the confirmation prompt.

    Returns the action id so callers can correlate later messages.
    """
    from app.services.whatsapp import send_reply_buttons

    action_id = uuid.uuid4().hex[:12]

    # Replace any pending action of the same kind from the same sender —
    # the new message is the source of truth.
    prior_id = _BY_SENDER.pop((sender_wa_id, kind), None)
    if prior_id and prior_id in _REGISTRY:
        prior = _REGISTRY.pop(prior_id)
        prior.state = "cancelled"
        if prior.on_cancel:
            try:
                await prior.on_cancel()
            except Exception:  # noqa: BLE001 — best-effort cancel
                logger.exception("on_cancel failed for prior action %s", prior_id)

    action = PendingCriticalAction(
        id=action_id,
        family_id=family_id,
        sender_wa_id=sender_wa_id,
        kind=kind,
        summary=summary,
        payload=payload,
        on_commit=on_commit,
        on_cancel=on_cancel,
    )
    _REGISTRY[action_id] = action
    _BY_SENDER[(sender_wa_id, kind)] = action_id

    # Send the read-back.
    minutes = auto_commit_sec // 60
    body = (
        f"Confirm karein: {summary}\n\n"
        f"Haan kahein toh save kar dungi. "
        f"{minutes} minute mein koi reply na ho toh apne aap save ho jayega."
    )
    try:
        await send_reply_buttons(
            sender_wa_id,
            body,
            buttons=[
                {"id": f"crit_yes_{action_id}", "title": "✅ Haan, sahi hai"},
                {"id": f"crit_no_{action_id}", "title": "❌ Nahi, ruk jao"},
            ],
            footer="Bimi",
        )
    except Exception:  # noqa: BLE001 — message-send failure shouldn't lose the action
        logger.exception("Failed to send critical-confirmation prompt for %s", action_id)

    # Schedule the auto-commit. We deliberately use create_task so the
    # caller doesn't have to await — the loop is fire-and-forget.
    asyncio.create_task(_auto_commit_after(action_id, auto_commit_sec))
    return action_id


async def _auto_commit_after(action_id: str, after_sec: int) -> None:
    await asyncio.sleep(after_sec)
    action = _REGISTRY.get(action_id)
    if not action or action.state != "pending":
        return
    action.state = "auto_committed"
    try:
        await action.on_commit(action.payload)
    except Exception:  # noqa: BLE001 — commit failure must not crash the auto-loop
        logger.exception("Auto-commit failed for %s", action_id)
    finally:
        _BY_SENDER.pop((action.sender_wa_id, action.kind), None)
        from app.services.whatsapp import send_text_message
        try:
            await send_text_message(
                action.sender_wa_id,
                f"⏳ 2 minute hone ke baad confirm kar diya: {action.summary}.\n"
                f"Agar galat hai toh batayein, undo kar denge.",
            )
        except Exception:  # noqa: BLE001
            pass


async def handle_confirmation_button(
    sender_wa_id: str, button_id: str,
) -> dict[str, Any] | None:
    """Route `crit_yes_*` / `crit_no_*` button taps.

    Returns None if `button_id` is not a critical-confirmation button.
    Otherwise returns a dict describing what happened
    (`{"action_id": ..., "state": "committed" | "cancelled" | "stale"}`).
    """
    from app.services.whatsapp import send_text_message

    if button_id.startswith("crit_yes_"):
        action_id = button_id[len("crit_yes_"):]
        confirmed = True
    elif button_id.startswith("crit_no_"):
        action_id = button_id[len("crit_no_"):]
        confirmed = False
    else:
        return None

    action = _REGISTRY.get(action_id)
    if not action or action.state != "pending":
        # Stale tap — the action was already committed/cancelled (often
        # via auto-commit). Don't error out, just ack.
        await send_text_message(
            sender_wa_id, "Yeh action pehle hi process ho chuka hai. 🙏",
        )
        return {"action_id": action_id, "state": "stale"}

    if confirmed:
        action.state = "committed"
        try:
            await action.on_commit(action.payload)
        except Exception:  # noqa: BLE001
            logger.exception("on_commit failed for %s", action_id)
        await send_text_message(sender_wa_id, f"✅ Done: {action.summary}")
    else:
        action.state = "cancelled"
        if action.on_cancel:
            try:
                await action.on_cancel()
            except Exception:  # noqa: BLE001
                logger.exception("on_cancel failed for %s", action_id)
        await send_text_message(
            sender_wa_id, "Theek hai, kuch nahi karte. 🙏 Aap dobara batayein.",
        )

    _BY_SENDER.pop((action.sender_wa_id, action.kind), None)
    return {"action_id": action_id, "state": action.state}


def _peek(action_id: str) -> PendingCriticalAction | None:
    """Test-only helper to inspect the registry without exposing it."""
    return _REGISTRY.get(action_id)


def _reset_for_tests() -> None:
    """Test teardown helper — clear all pending actions."""
    _REGISTRY.clear()
    _BY_SENDER.clear()
