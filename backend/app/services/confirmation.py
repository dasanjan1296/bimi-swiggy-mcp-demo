"""
Confirmation state machine.

Manages the conversation flow between Bimi and the parent on WhatsApp.
Ensures items are confirmed before being added to the cart, with graceful
degradation across confidence levels and input modalities.

State transitions:

    ┌─ Voice/Text/Image ─► EXTRACT ─┬─ High confidence ──► AWAITING_CONFIRMATION
    │                                ├─ Medium confidence ► AWAITING_CONFIRMATION (softer prompt)
    │                                └─ Low confidence ───► AWAITING_CLARIFICATION
    │
    ├─ ✅ "Sahi hai" ────────────────► RESOLVED → add to cart
    ├─ ❌ "Galat hai" ───────────────► AWAITING_ITEM_CORRECTION → walk through each item
    ├─ ➕ "Aur add karo" ────────────► RESOLVED → add to cart, keep cart open
    ├─ 🔄 "Dobara bolun" ───────────► AWAITING_CLARIFICATION → ask for retry
    │
    ├─ Item ✅ / ❌ / 🗑 ────────────► next item or RESOLVED
    ├─ List selection ───────────────► update item → AWAITING_CONFIRMATION
    │
    └─ New voice/text/image while pending ► treat as correction/addition
"""

import json
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.confirmation import ConfirmationState, PendingConfirmation
from app.schemas.intent import IntentResult
from app.services.batching import add_items_to_cart
from app.services.whatsapp import (
    send_cart_summary,
    send_high_confidence_confirmation,
    send_low_confidence_fallback,
    send_medium_confidence_confirmation,
    send_per_item_correction,
    send_text_message,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core: process a fresh extraction result through the confidence gate
# ---------------------------------------------------------------------------

async def handle_extraction(
    parent_id: uuid.UUID,
    family_id: uuid.UUID,
    wa_id: str,
    intent: IntentResult,
    db: AsyncSession,
):
    """
    After items are extracted (from voice, text, or image), decide what to do
    based on overall and per-item confidence.
    """
    # Expire any existing pending confirmation for this parent
    await _expire_active(parent_id, db)

    if not intent.items:
        # Nothing extracted — ask for clarification
        reorder = await _get_reorder_items(family_id, db)
        await send_low_confidence_fallback(wa_id, reorder)
        pc = _create_pending(parent_id, family_id, intent, ConfirmationState.AWAITING_CLARIFICATION)
        db.add(pc)
        await db.commit()
        return

    items_dicts = [item.model_dump() for item in intent.items]

    if intent.confidence >= settings.confidence_high:
        # High confidence — simple ✅/❌ confirmation
        result = await send_high_confidence_confirmation(wa_id, items_dicts)
        pc = _create_pending(parent_id, family_id, intent, ConfirmationState.AWAITING_CONFIRMATION)
        pc.sent_message_id = result.get("message_id")
        db.add(pc)
        await db.commit()

    elif intent.confidence >= settings.confidence_medium:
        # Medium confidence — softer confirmation with retry option
        result = await send_medium_confidence_confirmation(wa_id, items_dicts)
        pc = _create_pending(parent_id, family_id, intent, ConfirmationState.AWAITING_CONFIRMATION)
        pc.sent_message_id = result.get("message_id")
        db.add(pc)
        await db.commit()

    else:
        # Low confidence — show what we got but also offer alternatives
        if intent.items:
            result = await send_medium_confidence_confirmation(wa_id, items_dicts)
            pc = _create_pending(parent_id, family_id, intent, ConfirmationState.AWAITING_CONFIRMATION)
            pc.sent_message_id = result.get("message_id")
            db.add(pc)
        else:
            reorder = await _get_reorder_items(family_id, db)
            await send_low_confidence_fallback(wa_id, reorder)
            pc = _create_pending(parent_id, family_id, intent, ConfirmationState.AWAITING_CLARIFICATION)
            db.add(pc)
        await db.commit()


# ---------------------------------------------------------------------------
# Handle interactive replies (button taps, list selections)
# ---------------------------------------------------------------------------

async def handle_button_reply(
    parent_id: uuid.UUID,
    family_id: uuid.UUID,
    wa_id: str,
    button_id: str,
    db: AsyncSession,
):
    """Handle a reply-button tap from the parent."""
    pc = await _get_active(parent_id, db)
    if not pc:
        await send_text_message(wa_id, "Koi pending request nahi hai. Nayi voice note ya text bhejein!")
        return

    items = json.loads(pc.extracted_items_json)

    if button_id == "confirm_yes":
        # All items confirmed — add to cart
        await _resolve_and_add(pc, items, family_id, wa_id, db)

    elif button_id == "confirm_no":
        # Start per-item correction walk-through
        if len(items) == 1:
            # Only one item — ask for text/photo correction directly
            pc.state = ConfirmationState.AWAITING_CLARIFICATION
            await db.commit()
            await send_text_message(
                wa_id,
                "Koi baat nahi! Sahi item text mein likh kar bhejein, ya photo bhej dijiye."
            )
        else:
            pc.state = ConfirmationState.AWAITING_ITEM_CORRECTION
            pc.correction_item_index = 0
            await db.commit()
            await send_per_item_correction(wa_id, items[0], 0)

    elif button_id == "confirm_add":
        # Items are correct, add to cart, keep listening for more
        await _resolve_and_add(pc, items, family_id, wa_id, db, send_summary=True)

    elif button_id == "confirm_retry":
        # Parent wants to try again
        pc.state = ConfirmationState.AWAITING_CLARIFICATION
        pc.attempt_count += 1
        await db.commit()
        await send_text_message(
            wa_id,
            "Koi baat nahi! Dobara bol dijiye, ya text mein likh dijiye. 🙂"
        )

    elif button_id.startswith("item_ok_"):
        await _handle_item_correction(pc, items, wa_id, int(button_id.split("_")[-1]), "ok", db)

    elif button_id.startswith("item_wrong_"):
        await _handle_item_correction(pc, items, wa_id, int(button_id.split("_")[-1]), "wrong", db)

    elif button_id.startswith("item_remove_"):
        await _handle_item_correction(pc, items, wa_id, int(button_id.split("_")[-1]), "remove", db)

    elif button_id == "cart_send":
        # Parent wants to send cart to child now — trigger batching
        from app.services.batching import trigger_cart_for_family
        await trigger_cart_for_family(family_id, db)
        await send_text_message(wa_id, "Cart beta ko bhej diya! Woh approve karke order kar denge. 📤")

    elif button_id == "cart_add":
        await send_text_message(wa_id, "Aur kya chahiye? Voice note ya text bhej dijiye. 🎤")

    elif button_id == "cart_clear":
        from app.services.batching import clear_accumulating_cart
        await clear_accumulating_cart(family_id, db)
        await send_text_message(wa_id, "Cart khali kar diya! Nayi list bhejiye. 🗑")


async def handle_list_reply(
    parent_id: uuid.UUID,
    family_id: uuid.UUID,
    wa_id: str,
    list_id: str,
    list_title: str,
    db: AsyncSession,
):
    """Handle a list selection from the parent."""
    pc = await _get_active(parent_id, db)

    if list_id.startswith("reorder_"):
        # Parent picked an item from their reorder suggestions
        # Treat it as a confirmed item — add to cart directly
        items = [{"name": list_title, "brand": None, "quantity": 1, "unit": "pcs", "urgent": False}]
        await add_items_to_cart(family_id, items, db)
        await send_text_message(wa_id, f"✅ {list_title} cart mein add kar diya! Aur kuch chahiye?")

        if pc:
            pc.state = ConfirmationState.RESOLVED
            await db.commit()

    elif list_id.startswith("disambig_"):
        # Parent chose a specific variant during disambiguation
        if pc:
            items = json.loads(pc.extracted_items_json)
            idx = pc.correction_item_index or 0
            if idx < len(items):
                items[idx]["name"] = list_title
                items[idx]["confidence"] = 1.0
                pc.extracted_items_json = json.dumps(items)

                # Move to next item or resolve
                await _advance_item_correction(pc, items, wa_id, idx, db)


# ---------------------------------------------------------------------------
# Handle new input while a confirmation is pending
# ---------------------------------------------------------------------------

async def handle_new_input_during_pending(
    parent_id: uuid.UUID,
    family_id: uuid.UUID,
    wa_id: str,
    intent: IntentResult,
    db: AsyncSession,
):
    """
    Parent sent a new voice/text/image while we were waiting for a button tap.
    Interpret this as a correction or addition depending on the pending state.
    """
    pc = await _get_active(parent_id, db)
    if not pc:
        # No pending — treat as a fresh extraction
        await handle_extraction(parent_id, family_id, wa_id, intent, db)
        return

    if pc.state == ConfirmationState.AWAITING_CLARIFICATION:
        # This IS the clarification — treat as fresh extraction
        pc.state = ConfirmationState.EXPIRED
        await db.commit()
        await handle_extraction(parent_id, family_id, wa_id, intent, db)

    elif pc.state == ConfirmationState.AWAITING_ITEM_CORRECTION:
        # Correction for the current item
        if intent.items:
            items = json.loads(pc.extracted_items_json)
            idx = pc.correction_item_index or 0
            if idx < len(items):
                corrected = intent.items[0]
                items[idx] = corrected.model_dump()
                items[idx]["confidence"] = 1.0
                pc.extracted_items_json = json.dumps(items)
                await _advance_item_correction(pc, items, wa_id, idx, db)
        else:
            await send_text_message(wa_id, "Samajh nahi aaya. Kya aap text mein likh sakte hain?")

    elif pc.state == ConfirmationState.AWAITING_CONFIRMATION:
        # Parent sent something new instead of tapping buttons.
        # Could be additional items — merge them.
        if intent.items:
            existing = json.loads(pc.extracted_items_json)
            new_items = [item.model_dump() for item in intent.items]
            merged = existing + new_items
            pc.extracted_items_json = json.dumps(merged)
            pc.overall_confidence = min(pc.overall_confidence, intent.confidence)
            await db.commit()

            # Re-confirm with merged list
            result = await send_high_confidence_confirmation(wa_id, merged)
            pc.sent_message_id = result.get("message_id")
            await db.commit()


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

async def _get_active(parent_id: uuid.UUID, db: AsyncSession) -> PendingConfirmation | None:
    """Get the active (non-resolved, non-expired) confirmation for a parent."""
    result = await db.execute(
        select(PendingConfirmation).where(
            PendingConfirmation.parent_id == parent_id,
            PendingConfirmation.state.notin_([
                ConfirmationState.RESOLVED,
                ConfirmationState.EXPIRED,
            ]),
        ).order_by(PendingConfirmation.created_at.desc()).limit(1)
    )
    return result.scalar_one_or_none()


async def _expire_active(parent_id: uuid.UUID, db: AsyncSession):
    """Expire any existing active confirmations for a parent."""
    result = await db.execute(
        select(PendingConfirmation).where(
            PendingConfirmation.parent_id == parent_id,
            PendingConfirmation.state.notin_([
                ConfirmationState.RESOLVED,
                ConfirmationState.EXPIRED,
            ]),
        )
    )
    for pc in result.scalars().all():
        pc.state = ConfirmationState.EXPIRED
    await db.flush()


def _create_pending(
    parent_id: uuid.UUID,
    family_id: uuid.UUID,
    intent: IntentResult,
    state: ConfirmationState,
) -> PendingConfirmation:
    return PendingConfirmation(
        parent_id=parent_id,
        family_id=family_id,
        state=state,
        extracted_items_json=json.dumps([item.model_dump() for item in intent.items]),
        source_type=intent.source,
        raw_transcript=intent.raw_transcript,
        overall_confidence=intent.confidence,
    )


async def _resolve_and_add(
    pc: PendingConfirmation,
    items: list[dict],
    family_id: uuid.UUID,
    wa_id: str,
    db: AsyncSession,
    send_summary: bool = False,
):
    """Mark confirmation as resolved and add items to the cart."""
    pc.state = ConfirmationState.RESOLVED
    await db.flush()

    # Mark conversation messages as confirmed for context tracking
    from app.services.context_memory import mark_message_confirmed
    await mark_message_confirmed(pc.parent_id, db)

    await add_items_to_cart(family_id, items, db)

    if send_summary:
        await send_cart_summary(wa_id, items)
    else:
        count = len(items)
        await send_text_message(
            wa_id,
            f"✅ {count} {'item' if count == 1 else 'items'} cart mein add ho gaye! "
            "Aur kuch chahiye toh voice note ya text bhej dijiye."
        )
    await db.commit()


async def _handle_item_correction(
    pc: PendingConfirmation,
    items: list[dict],
    wa_id: str,
    item_index: int,
    action: str,
    db: AsyncSession,
):
    """Handle per-item correction during the item walk-through."""
    if action == "remove":
        removed_item = items.pop(item_index)
        pc.extracted_items_json = json.dumps(items)

        # Track the rejection
        from app.services.context_memory import record_rejection
        await record_rejection(
            pc.family_id,
            removed_item.get("name", ""),
            removed_item.get("brand"),
            "removed",
            db,
        )

        if not items:
            pc.state = ConfirmationState.AWAITING_CLARIFICATION
            await db.commit()
            await send_text_message(wa_id, "Sab items hata diye. Naye items bhejiye!")
            return

    elif action == "wrong":
        # Track rejection of the wrong item/brand
        wrong_item = items[item_index] if item_index < len(items) else None
        if wrong_item:
            from app.services.context_memory import record_rejection
            await record_rejection(
                pc.family_id,
                wrong_item.get("name", ""),
                wrong_item.get("brand"),
                "wrong_item",
                db,
            )

        await send_text_message(
            wa_id,
            f"Item #{item_index + 1} galat hai. Sahi item text mein likh dijiye ya photo bhejiye."
        )
        pc.correction_item_index = item_index
        await db.commit()
        return

    # "ok" or "remove" — advance to next item
    await _advance_item_correction(pc, items, wa_id, item_index, db)


async def _advance_item_correction(
    pc: PendingConfirmation,
    items: list[dict],
    wa_id: str,
    current_index: int,
    db: AsyncSession,
):
    """Move to the next item in the correction walk-through, or finish."""
    next_index = current_index + 1
    if next_index < len(items):
        pc.correction_item_index = next_index
        pc.extracted_items_json = json.dumps(items)
        await db.commit()
        await send_per_item_correction(wa_id, items[next_index], next_index)
    else:
        # All items reviewed — re-confirm the final list
        pc.extracted_items_json = json.dumps(items)
        pc.state = ConfirmationState.AWAITING_CONFIRMATION
        pc.correction_item_index = None
        await db.commit()
        result = await send_high_confidence_confirmation(wa_id, items)
        pc.sent_message_id = result.get("message_id")
        await db.commit()


async def _get_reorder_items(family_id: uuid.UUID, db: AsyncSession, parent_id: uuid.UUID | None = None) -> list[dict] | None:
    """
    Get reorder suggestions for the low-confidence fallback list.
    Person-aware: if parent_id is provided, prioritize items from
    the person's correction_history and favorite patterns first.
    """
    from app.models.person_context import PersonContext
    from app.services.preferences import get_family_preferences

    items = []

    if parent_id:
        result = await db.execute(
            select(PersonContext).where(PersonContext.parent_id == parent_id)
        )
        pctx = result.scalar_one_or_none()
        if pctx and pctx.correction_history:
            for word, resolved in list(pctx.correction_history.items())[:5]:
                items.append({"item_name": resolved, "brand": None, "quantity": 1, "unit": "pcs"})

    prefs = await get_family_preferences(family_id, db)
    if prefs:
        sorted_prefs = sorted(prefs, key=lambda p: p.order_count, reverse=True)
        for p in sorted_prefs[:10 - len(items)]:
            items.append({
                "item_name": p.item_name,
                "brand": p.brand,
                "quantity": p.quantity,
                "unit": p.unit,
            })

    return items if items else None
