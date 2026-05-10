"""
WhatsApp webhook router — handles all inbound message types.

Supported:
- Voice notes → transcribe → extract → confirm
- Text messages → extract → confirm
- Images (product photos) → vision identify → extract → confirm
- Interactive replies (button taps) → route to confirmation handler
- Interactive replies (list selections) → route to confirmation handler
"""

import json
import logging
from datetime import UTC

from fastapi import APIRouter, BackgroundTasks, Query, Request, Response
from pydantic import ValidationError
from sqlalchemy import select

from app.config import settings
from app.db import async_session
from app.models.family import Parent
from app.schemas.whatsapp import WhatsAppMessage, WhatsAppWebhookPayload

router = APIRouter(tags=["webhook"])
logger = logging.getLogger(__name__)


@router.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """WhatsApp webhook verification (GET challenge-response).

    Per Meta's spec: respond with `hub.challenge` plain-text (200) on success,
    HTTP 403 on token mismatch. A 200 with body `{"error": ...}` was the
    previous bug — Meta would mark the webhook as verified anyway because
    the response didn't echo the challenge but didn't fail either, leaving
    a confusing partial state.
    """
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        if hub_challenge is None:
            return Response(content="", status_code=200, media_type="text/plain")
        return Response(content=hub_challenge, status_code=200, media_type="text/plain")
    return Response(
        content="Verification failed", status_code=403, media_type="text/plain",
    )


@router.post("/webhook")
async def receive_webhook(request: Request, background_tasks: BackgroundTasks):
    """Receive inbound WhatsApp messages and dispatch by type.

    Loop 11 fix: signature verification is now invoked here. Previously
    the helper existed in `app/main.py` but was DEAD CODE — the receive
    handler never called it, which meant anyone could POST arbitrary
    payloads to /api/webhook and we'd treat them as legitimate Meta
    traffic. Massive forgery hole.

    Robustness contract: this endpoint MUST NEVER 5xx. Meta retries 5xx
    deliveries, so a single malformed payload becomes a thundering herd.
    Any payload we can't parse is logged + ack'd with 200 so Meta moves on.
    """
    # Read the raw bytes ONCE so signature verification + JSON parse
    # operate on the same buffer.
    raw_body = await request.body()

    # Signature verification. In production with the secret configured,
    # this fails closed on any signature mismatch. In dev (no secret),
    # the helper allows through (returns True) so local testing works
    # without Meta's real signing keys.
    from app.main import verify_whatsapp_signature

    sig = request.headers.get("X-Hub-Signature-256", "")
    if not verify_whatsapp_signature(raw_body, sig):
        logger.warning(
            "Webhook: signature verification failed (sig=%r, body_len=%d)",
            sig[:16], len(raw_body),
        )
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Invalid signature")

    try:
        body = json.loads(raw_body) if raw_body else {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Webhook: failed to parse JSON body — %s", exc)
        return {"status": "received", "ignored": "invalid_json"}

    if not isinstance(body, dict):
        logger.warning("Webhook: top-level body is not an object — %r", type(body).__name__)
        return {"status": "received", "ignored": "non_object_body"}

    try:
        payload = WhatsAppWebhookPayload(**body)
    except ValidationError as exc:
        logger.warning("Webhook: payload schema mismatch — %s", exc)
        return {"status": "received", "ignored": "schema_mismatch"}

    if not payload.entry:
        return {"status": "no entries"}

    # Loop 9: dedup table prevents replay attacks + Meta webhook retries
    # from double-processing the same message. We INSERT the message_id
    # eagerly; on conflict, we skip dispatch.
    from sqlalchemy.exc import IntegrityError

    from app.db import async_session
    from app.models.whatsapp_dedup import WhatsAppMessageDedup

    deduped_count = 0
    dispatched_count = 0

    for entry in payload.entry:
        if not entry or not entry.changes:
            continue
        for change in entry.changes:
            if not change or not change.value or not change.value.messages:
                continue
            for message in change.value.messages:
                if message is None:
                    continue
                try:
                    sender = message.from_ or (
                        change.value.contacts[0].wa_id
                        if change.value.contacts else None
                    )
                except (AttributeError, IndexError):
                    sender = None
                if not sender:
                    continue

                # Replay protection. If the message has no id, dispatch
                # without dedup (Meta always sets it; missing id means
                # this is a synthetic test payload).
                msg_id = getattr(message, "id", None)
                if msg_id:
                    try:
                        async with async_session() as dedup_db:
                            dedup_db.add(WhatsAppMessageDedup(message_id=msg_id))
                            await dedup_db.commit()
                    except IntegrityError:
                        deduped_count += 1
                        logger.info(
                            "Webhook: deduped replayed message %s from %s",
                            msg_id, sender,
                        )
                        continue
                    except Exception:  # noqa: BLE001
                        # Dedup failure should NOT block dispatch — log and proceed.
                        logger.exception(
                            "Webhook: dedup write failed for %s; dispatching anyway",
                            msg_id,
                        )

                dispatched_count += 1
                background_tasks.add_task(_dispatch_message, sender, message)

    return {
        "status": "received",
        "dispatched": dispatched_count,
        "deduped": deduped_count,
    }


# Loop 14: hard timeout per WhatsApp dispatch. Without this, a single
# slow downstream call (OpenAI 60s timeout, Sarvam 60s, slow DB query)
# blocks one of FastAPI's BackgroundTask slots for the full duration.
# Under burst load this is a worker-starvation vector. 45s is generous
# enough for legit traffic (transcription + LLM intent extraction +
# DB writes) and tight enough that hung calls fail fast.
_DISPATCH_TIMEOUT_SEC = 45.0


async def _dispatch_message(sender_wa_id: str, message: WhatsAppMessage):
    """Route each message type to the appropriate handler.

    Wrapped in `asyncio.wait_for` so a single slow message can't block
    the worker indefinitely. On timeout we log and the dedup row's
    `processed_at` stays NULL — a Loop 16 cleanup task will re-dispatch
    rows that have been pending for > 5 min.
    """
    import asyncio
    from datetime import UTC as _UTC
    from datetime import datetime as _dt

    msg_id = getattr(message, "id", None)
    dispatch_succeeded = False

    try:
        await asyncio.wait_for(
            _dispatch_message_inner(sender_wa_id, message),
            timeout=_DISPATCH_TIMEOUT_SEC,
        )
        dispatch_succeeded = True
    except TimeoutError:
        logger.error(
            "Dispatch TIMEOUT (>%ss) for sender %s message_id=%s",
            _DISPATCH_TIMEOUT_SEC, sender_wa_id, msg_id,
        )

    # Loop 15: mark the dedup row as processed ONLY on success. This
    # leaves the row at processed_at=NULL on timeout / crash so a
    # cleanup re-dispatcher can re-attempt. (Re-dispatcher itself is
    # a Loop 16 deliverable — for now this is the source of truth.)
    if dispatch_succeeded and msg_id:
        try:
            from sqlalchemy import update as _upd

            from app.models.whatsapp_dedup import WhatsAppMessageDedup
            async with async_session() as dedup_db:
                await dedup_db.execute(
                    _upd(WhatsAppMessageDedup)
                    .where(WhatsAppMessageDedup.message_id == msg_id)
                    .values(processed_at=_dt.now(_UTC))
                )
                await dedup_db.commit()
        except Exception:  # noqa: BLE001
            logger.exception(
                "Failed to mark dedup processed_at for %s — observable "
                "via the dedup-cleanup task", msg_id,
            )


async def _dispatch_message_inner(sender_wa_id: str, message: WhatsAppMessage):
    """Inner dispatch — wrapped by `_dispatch_message` for timeout enforcement."""
    try:
        async with async_session() as db:
            # --- Shared cook (multi-household) routing ---
            from app.services.cook_context import (
                lookup_shared_cook,
                resolve_household,
                switch_active_household,
            )
            shared_cook = await lookup_shared_cook(sender_wa_id, db)
            if shared_cook:
                msg_text = _extract_text_for_routing(message)

                # Handle household-switch button taps before full resolution
                if message.type == "interactive" and message.interactive:
                    handled = await _handle_shared_cook_interactive(
                        shared_cook, message.interactive, db,
                    )
                    if handled:
                        return

                ctx = await resolve_household(shared_cook, msg_text, db)

                if ctx.resolution_method == "ambiguous":
                    from app.services.cook_disambiguation import send_household_picker
                    await send_household_picker(shared_cook, db)
                    return

                if ctx.resolution_method == "no_households":
                    from app.services.whatsapp import send_text_message
                    await send_text_message(
                        sender_wa_id,
                        "Abhi aap kisi bhi ghar se connected nahi hain. 🙏",
                    )
                    return

                if ctx.resolution_method == "explicit":
                    await switch_active_household(shared_cook, ctx.family_id, db)
                    await db.commit()

                if not ctx.parent:
                    logger.warning(
                        "SharedCook %s has no Parent row for family %s",
                        shared_cook.id, ctx.family_id,
                    )
                    return

                # Update recency tracking for non-explicit resolutions
                if ctx.resolution_method != "explicit":
                    shared_cook.active_family_id = ctx.family_id
                    from datetime import datetime
                    shared_cook.last_switched_at = datetime.now(UTC)
                    await db.flush()

                parent = ctx.parent
                await _dispatch_parent_message(parent, message, db)
                return

            # --- Single-household parent (original flow) ---
            parent = await _lookup_parent(sender_wa_id, db)
            if not parent:
                logger.warning("Unknown sender: %s", sender_wa_id)
                return

            await _dispatch_parent_message(parent, message, db)

    except Exception:
        logger.exception("Error processing message from %s", sender_wa_id)


async def _dispatch_parent_message(parent: Parent, message: WhatsAppMessage, db):
    """Dispatch a resolved parent's message to the appropriate type handler."""
    msg_type = message.type

    if msg_type == "audio" and message.audio:
        await _handle_voice(parent, message.audio.id, db)

    elif msg_type == "text" and message.text:
        await _handle_text(parent, message.text.body, db)

    elif msg_type == "image" and message.image:
        caption = message.image.caption
        await _handle_image(parent, message.image.id, message.image.mime_type, caption, db)

    elif msg_type == "interactive" and message.interactive:
        await _handle_interactive(parent, message.interactive, db)

    else:
        logger.debug("Ignoring message type: %s", msg_type)


def _extract_text_for_routing(message: WhatsAppMessage) -> str | None:
    """Pull the text content from a message for context-resolution heuristics."""
    if message.type == "text" and message.text:
        return message.text.body
    if message.type == "interactive" and message.interactive:
        if message.interactive.button_reply:
            return message.interactive.button_reply.title
        if message.interactive.list_reply:
            return message.interactive.list_reply.title
    return None


async def _handle_shared_cook_interactive(shared_cook, interactive, db) -> bool:
    """
    Intercept household-switch button taps (cook_switch_*) before normal dispatch.
    Returns True if the button was handled here, False to continue normal flow.
    """
    SWITCH_PREFIX = "cook_switch_"
    BROADCAST_PREFIX = "cook_broadcast_"

    if interactive.type != "button_reply" or not interactive.button_reply:
        return False

    btn_id = interactive.button_reply.id

    if btn_id.startswith(SWITCH_PREFIX):
        import uuid as uuid_mod

        from app.services.cook_context import household_divider, switch_active_household
        from app.services.whatsapp import send_text_message

        family_id_str = btn_id[len(SWITCH_PREFIX):]
        try:
            family_id = uuid_mod.UUID(family_id_str)
        except ValueError:
            return True

        hh = await switch_active_household(shared_cook, family_id, db)
        await db.commit()
        if hh:
            await send_text_message(
                shared_cook.whatsapp_id,
                f"{household_divider(hh.household_label)}\n"
                f"Switched! Ab {hh.household_label} ke liye baat karein. 👍",
            )
        return True

    if btn_id.startswith(BROADCAST_PREFIX):
        from app.services.cook_context import _get_parent_for_family
        from app.services.cook_disambiguation import handle_absence_broadcast

        affected_ids = await handle_absence_broadcast(
            shared_cook, btn_id, "", db,
        )
        for fid in affected_ids:
            parent = await _get_parent_for_family(shared_cook.whatsapp_id, fid, db)
            if parent:
                await _handle_absence(parent, "nahi aa paungi", db)
        return True

    return False


# NOTE: pool-cook job-handling helpers removed with the Instacook marketplace.


# ---------------------------------------------------------------------------
# Household label helper (multi-household cooks)
# ---------------------------------------------------------------------------

async def _get_label(parent: Parent, db) -> str | None:
    """Return the household label if this parent is a multi-household cook."""
    from app.services.cook_context import get_household_label_for_parent
    try:
        return await get_household_label_for_parent(parent, db)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Message type handlers
# ---------------------------------------------------------------------------

async def _handle_voice(parent: Parent, media_id: str, db):
    """Voice note → transcribe → low-conf gate → domain routing.

    F3 fix (multimodal validation): when transcription confidence is below
    `voice_low_confidence_threshold` AND we have *some* transcript text,
    surface the best-guess to the user instead of black-holing the message
    with a generic "samajh nahi aaya". This keeps the conversation alive.
    """
    from app.services.transcription import transcribe_audio
    from app.services.whatsapp import download_media, send_low_confidence_fallback

    audio_bytes = await download_media(media_id)
    result = await transcribe_audio(audio_bytes, language=parent.language)

    if not result.transcript.strip():
        logger.warning(
            "Empty transcript for voice note from %s (source=%s)",
            parent.whatsapp_id, result.source,
        )
        await send_low_confidence_fallback(parent.whatsapp_id)
        return

    # F3: low confidence with a partial transcript → best-guess prompt.
    if result.confidence < settings.voice_low_confidence_threshold:
        logger.info(
            "Low-confidence voice from %s (conf=%.2f) — sending best-guess fallback",
            parent.whatsapp_id, result.confidence,
        )
        await send_low_confidence_fallback(
            parent.whatsapp_id, best_guess=result.transcript,
        )
        return

    # Slice 3: instead of dispatching immediately, stage the transcript
    # in a per-sender coalesce buffer. The buffer auto-flushes after
    # `COALESCE_WINDOW_SEC` seconds of silence, concatenating any
    # additional voice notes that arrive within the window. This stops
    # rapid-fire bursts ("doodh... aur paneer... aur anda") from being
    # extracted as three fragmented intents.
    from app.services.voice_coalesce import schedule_voice_dispatch
    await schedule_voice_dispatch(
        parent_id=parent.id,
        family_id=parent.family_id,
        sender_wa_id=parent.whatsapp_id,
        language=parent.language or "hi",
        transcript=result.transcript,
        confidence=result.confidence,
    )


async def _handle_text(parent: Parent, text_body: str, db):
    """Text message → detect domain (ride vs grocery) → appropriate flow."""
    # HCG life event detection on every text message
    try:
        from app.services.temporal_engine import detect_life_events, handle_life_event
        events = detect_life_events(text_body)
        for event in events:
            await handle_life_event(parent.family_id, parent.id, event, db)
    except Exception:  # noqa: BLE001 — best-effort life-event detection
        logger.exception("life-event detection failed for parent %s", parent.id)

    await _route_text_input(parent, text_body, "text", 1.0, db)


async def _route_text_input(
    parent: Parent, text: str, source: str, confidence: float, db
):
    """
    Central routing — priority order:
    1. Meal ready confirmation (cook says "ban gaya" / "ho gaya" / "ready")
    2. Meal query (household mode: cook asks "aaj kya banega?")
    3. Absence notification (household mode: "nahi aaunga")
    4. Standing instruction (user/cook issuing a recurring directive)
    5. Behavioral feedback (user/cook giving feedback about Bimi)
    6. Grocery/supply request (existing flow)
    """
    from app.models.confirmation import ConfirmationState, PendingConfirmation
    from app.services.confirmation import handle_extraction, handle_new_input_during_pending
    from app.services.context_memory import record_conversation_message
    from app.services.intent import extract_intent
    from app.services.recipe_link_handler import (
        handle_recipe_link,
        maybe_handle_pending_dish_reply,
        might_be_recipe_link,
    )

    # Learn communication patterns from every message
    try:
        from app.services.comm_adapter import learn_from_message
        await learn_from_message(parent.family_id, "parent", parent.id, text, source, db)
    except Exception:  # noqa: BLE001 — best-effort comm-adapter learning
        logger.exception("comm_adapter.learn_from_message failed for parent %s", parent.id)

    # 0a. Recipe link share (URL anywhere in message). Routed before
    # the grocery / meal-query / instruction handlers because a URL is
    # a strongly-typed signal — once we see one, the message is about
    # a recipe, not a shopping list.
    if might_be_recipe_link(text):
        await record_conversation_message(
            parent.id, parent.family_id, source, text, None, confidence, db
        )
        await handle_recipe_link(parent, text, db)
        return

    # 0b. Pending dish-name reply (member just answered "konsa dish?"
    # after sharing a URL whose dish we couldn't infer). Must run
    # before generic intent extraction so a short reply like
    # "paneer butter masala" doesn't get parsed as a grocery item.
    if await maybe_handle_pending_dish_reply(parent, text, db):
        await record_conversation_message(
            parent.id, parent.family_id, source, text, None, confidence, db
        )
        return

    # 1. Meal ready confirmation (cook says "ban gaya" / "ho gaya" / "ready")
    if _might_be_meal_ready(text) and parent.role == "cook":
        await record_conversation_message(
            parent.id, parent.family_id, source, text, None, confidence, db
        )
        await _handle_meal_ready_text(parent, db)
        return

    # 3. Meal query (household mode — cook asking what to make)
    if _might_be_meal_query(text) and parent.role in ("cook", "parent"):
        await record_conversation_message(
            parent.id, parent.family_id, source, text, None, confidence, db
        )
        await _handle_meal_query(parent, text, db)
        return

    # 3a. Pending ETA reply — cook tapped "Late hoongi" earlier and
    # we asked for an arrival time. The next message they send within
    # the TTL is interpreted as the ETA. Routed before the generic
    # absence check so a reply like "10 baje" doesn't get re-classified.
    from app.services.attendance import pop_pending_eta
    pending_eta = await pop_pending_eta(parent.whatsapp_id) if parent.role != "parent" else None
    if pending_eta is not None:
        await record_conversation_message(
            parent.id, parent.family_id, source, text, None, confidence, db
        )
        await _handle_late_arrival_eta(parent, text, db)
        return

    # 3b. Proactive partial-day deviations — cook says "doctor jaana
    # hai 2 baje" or "jaldi nikal jaungi". Surfaced to the parent
    # without triggering the replacement-booking flow.
    from app.services.attendance import (
        might_be_early_leave,
        might_be_late_arrival,
    )
    if parent.role != "parent" and might_be_early_leave(text):
        await record_conversation_message(
            parent.id, parent.family_id, source, text, None, confidence, db
        )
        await _handle_early_leave(parent, text, db)
        return
    if parent.role != "parent" and might_be_late_arrival(text):
        await record_conversation_message(
            parent.id, parent.family_id, source, text, None, confidence, db
        )
        await _handle_late_arrival_text(parent, text, db)
        return

    # 4. Absence notification (household mode — househelp reporting absence)
    from app.services.absence import might_be_absence
    if might_be_absence(text) and parent.role != "parent":
        await record_conversation_message(
            parent.id, parent.family_id, source, text, None, confidence, db
        )
        # Multi-household cook: offer broadcast picker before recording
        from app.services.cook_context import get_active_households as _get_active
        from app.services.cook_context import lookup_shared_cook
        sc = await lookup_shared_cook(parent.whatsapp_id, db)
        if sc:
            hhs = await _get_active(sc, db)
            if len(hhs) > 1:
                from app.services.cook_disambiguation import send_absence_picker
                await send_absence_picker(sc, db, text[:50])
                return
        await _handle_absence(parent, text, db)
        return

    # 5. Standing instruction detection
    if _might_be_instruction(text):
        await record_conversation_message(
            parent.id, parent.family_id, source, text, None, confidence, db
        )
        await _handle_instruction(parent, text, db)
        return

    # 6. Behavioral feedback about Bimi
    from app.services.feedback_metabolism import might_be_feedback
    if might_be_feedback(text):
        await record_conversation_message(
            parent.id, parent.family_id, source, text, None, confidence, db
        )
        await _handle_feedback(parent, text, db)
        return

    # 7. Grocery/supply flow (existing)
    # F2: multi-intent splitter — long voice notes ("doodh aur paneer aur
    # chawal") were collapsing into a single mushed item. We now run
    # extract_intent per logical unit and merge the items.
    from app.schemas.intent import IntentResult
    from app.services.multi_intent import is_likely_multi_intent, split_intents

    if source == "voice" and is_likely_multi_intent(text):
        units = split_intents(text)
        if len(units) > 1:
            sub_results = []
            for unit in units:
                sub = await extract_intent(
                    unit,
                    family_id=parent.family_id,
                    parent_id=parent.id,
                    source=source,
                    transcript_confidence=confidence,
                )
                sub_results.append(sub)
            merged_items = []
            seen_names = set()
            for sub in sub_results:
                for it in sub.items:
                    key = (it.name.lower(), (it.brand or "").lower())
                    if key in seen_names:
                        continue
                    seen_names.add(key)
                    merged_items.append(it)
            avg_conf = (
                sum(s.confidence for s in sub_results) / len(sub_results)
                if sub_results else 0.0
            )
            intent = IntentResult(
                items=merged_items,
                raw_transcript=text,
                language_detected=(sub_results[0].language_detected if sub_results else "hi"),
                confidence=round(avg_conf, 2),
                source=source,
            )
        else:
            intent = await extract_intent(
                text, family_id=parent.family_id, parent_id=parent.id,
                source=source, transcript_confidence=confidence,
            )
    else:
        intent = await extract_intent(
            text, family_id=parent.family_id, parent_id=parent.id,
            source=source, transcript_confidence=confidence,
        )

    extracted_dicts = [item.model_dump() for item in intent.items] if intent.items else None
    await record_conversation_message(
        parent.id, parent.family_id, source, text, extracted_dicts, confidence, db
    )

    from sqlalchemy import select as sa_select
    active = await db.execute(
        sa_select(PendingConfirmation).where(
            PendingConfirmation.parent_id == parent.id,
            PendingConfirmation.state.notin_([
                ConfirmationState.RESOLVED,
                ConfirmationState.EXPIRED,
            ]),
        ).limit(1)
    )
    if active.scalar_one_or_none():
        await handle_new_input_during_pending(
            parent.id, parent.family_id, parent.whatsapp_id, intent, db
        )
    else:
        await handle_extraction(parent.id, parent.family_id, parent.whatsapp_id, intent, db)


async def _handle_image(parent: Parent, media_id: str, mime_type: str | None, caption: str | None, db):
    """
    Image → GPT-4 Vision to identify product → extract intent → confirmation flow.

    If the image has a caption, it's used as additional context.
    """
    from app.services.confirmation import handle_extraction
    from app.services.image_recognition import identify_product_from_image
    from app.services.intent import extract_intent
    from app.services.whatsapp import download_media, send_text_message

    image_bytes = await download_media(media_id)
    vision_result = await identify_product_from_image(
        image_bytes, mime_type=mime_type or "image/jpeg"
    )

    if not vision_result.get("items"):
        label = await _get_label(parent, db)
        await send_text_message(
            parent.whatsapp_id,
            "Photo se item samajh nahi aaya. 🤔\n"
            "Kya aap text mein likh sakte hain kya chahiye?",
            household_label=label,
        )
        return

    # Build a description to feed to the intent engine
    description = vision_result.get("description", "")
    if caption:
        description = f"{caption}. {description}"

    # If the vision model identified items directly, use them
    if vision_result.get("is_handwritten_list"):
        # Handwritten list — extract all items via intent engine
        item_names = ", ".join(i.get("name", "") for i in vision_result["items"])
        intent = await extract_intent(
            f"Handwritten grocery list: {item_names}",
            family_id=parent.family_id,
            parent_id=parent.id,
            source="image",
        )
    else:
        intent = await extract_intent(
            f"Photo of product: {description}",
            family_id=parent.family_id,
            parent_id=parent.id,
            source="image",
        )

    await handle_extraction(parent.id, parent.family_id, parent.whatsapp_id, intent, db)


async def _handle_interactive(parent: Parent, interactive, db):
    """Handle button taps and list selections — route grocery / meal-ready / ingredient-check buttons."""
    MEAL_READY_BUTTON_PREFIXES = ("meal_ready_yes_", "meal_ready_no_")
    INGREDIENT_CHECK_PREFIXES = ("ingcheck_confirm_",)
    CRITICAL_CONFIRM_PREFIXES = ("crit_yes_", "crit_no_")
    ATTENDANCE_BUTTON_PREFIXES = ("attend_yes_", "attend_no_", "attend_late_")

    if interactive.type == "button_reply" and interactive.button_reply:
        btn_id = interactive.button_reply.id

        # Onboarding tap (Haan / Galat number) — routed first so the
        # rest of the dispatcher doesn't have to know about it.
        from app.services.cook_onboarding import maybe_handle_onboarding_button
        if await maybe_handle_onboarding_button(btn_id, db):
            return

        if btn_id.startswith(INGREDIENT_CHECK_PREFIXES):
            from app.services.ingredient_check import handle_confirmation_button
            await handle_confirmation_button(parent.whatsapp_id, btn_id, db)
            return

        if btn_id.startswith(MEAL_READY_BUTTON_PREFIXES):
            await _handle_meal_ready_button(parent, btn_id, db)
            return

        if btn_id.startswith(ATTENDANCE_BUTTON_PREFIXES):
            await _handle_attendance_button(parent, btn_id, db)
            return

        if btn_id.startswith(CRITICAL_CONFIRM_PREFIXES):
            # F4 fix (multimodal validation): critical-action confirmation
            # loop. Routed before the generic confirmation handler so the
            # 2-min auto-commit can settle correctly on the user's tap.
            from app.services.critical_confirmation import (
                handle_confirmation_button as handle_critical_button,
            )
            await handle_critical_button(parent.whatsapp_id, btn_id)
            return

        from app.services.confirmation import handle_button_reply
        await handle_button_reply(
            parent.id, parent.family_id, parent.whatsapp_id, btn_id, db
        )

    elif interactive.type == "list_reply" and interactive.list_reply:
        list_id = interactive.list_reply.id
        if list_id.startswith("ingcheck_"):
            from app.services.ingredient_check import handle_list_selection
            await handle_list_selection(parent.whatsapp_id, [list_id], db)
        else:
            from app.services.confirmation import handle_list_reply
            await handle_list_reply(
                parent.id,
                parent.family_id,
                parent.whatsapp_id,
                list_id,
                interactive.list_reply.title,
                db,
            )


# ---------------------------------------------------------------------------
# Meal ready confirmation handler
# ---------------------------------------------------------------------------

async def _handle_meal_ready_button(parent: Parent, btn_id: str, db):
    """Route meal_ready_yes / meal_ready_no buttons to the confirmation service."""
    import uuid as uuid_mod

    from app.services.meal_ready_check import handle_meal_ready_response

    is_ready = btn_id.startswith("meal_ready_yes_")
    prefix = "meal_ready_yes_" if is_ready else "meal_ready_no_"
    plan_id_str = btn_id[len(prefix):]

    try:
        plan_id = uuid_mod.UUID(plan_id_str)
    except ValueError:
        logger.warning("Invalid plan_id in meal_ready button: %s", btn_id)
        return

    await handle_meal_ready_response(plan_id, is_ready, parent.whatsapp_id, db)
    await db.commit()


async def _handle_attendance_button(parent: Parent, btn_id: str, db):
    """Route the morning attendance check-in (Haan / Nahi / Late) buttons."""
    from app.services.attendance import stash_pending_eta
    from app.services.whatsapp import send_text_message

    if btn_id.startswith("attend_yes_"):
        await send_text_message(
            parent.whatsapp_id, "Theek hai! Aaj milte hain. 🙏",
        )
        return

    if btn_id.startswith("attend_no_"):
        # Reuse the established absence flow — records HousehelpAbsence,
        # notifies the parent, and (per spec) does NOT trigger replacement
        # booking for the partial-day case (attend_no is a full-day absence).
        await _handle_absence(parent, "aaj nahi aa paungi", db)
        return

    if btn_id.startswith("attend_late_"):
        # Stash a pending-ETA marker. The next text/voice from this
        # cook in the next 30 minutes is interpreted as their ETA and
        # gets recorded as `late_arrival_time`.
        await stash_pending_eta(parent.whatsapp_id, str(parent.id))
        await send_text_message(
            parent.whatsapp_id,
            "Theek hai. Kitne baje aaogi? Voice note ya text bhej dijiye.",
        )
        return


# ---------------------------------------------------------------------------
# Meal ready text detection
# ---------------------------------------------------------------------------

MEAL_READY_KEYWORDS = [
    "ban gaya", "ban gaye", "ban gayi",
    "ho gaya", "ho gaye", "ho gayi",
    "ready", "ready hai", "tayyar", "tayyar hai",
    "khana ban gaya", "khana ready",
    "ban chuka", "ban chuki",
    "done", "meal ready", "food ready",
    "ho chuka", "ho chuki",
]


def _might_be_meal_ready(text: str) -> bool:
    """Check if a cook is confirming the meal is ready via free text."""
    text_lower = text.lower().strip()
    return any(kw in text_lower for kw in MEAL_READY_KEYWORDS)


async def _handle_meal_ready_text(parent: Parent, db):
    """Find the active COOKING plan for this cook's family and mark it cooked."""
    from datetime import date as date_type

    from sqlalchemy import and_
    from sqlalchemy import select as sa_select

    from app.models.meal_plan import MealPlan, MealPlanStatus
    from app.services.meal_ready_check import handle_meal_ready_response

    today = date_type.today()
    result = await db.execute(
        sa_select(MealPlan).where(
            and_(
                MealPlan.family_id == parent.family_id,
                MealPlan.date == today,
                MealPlan.status == MealPlanStatus.COOKING,
            )
        ).order_by(MealPlan.cook_arrival_time.desc()).limit(1)
    )
    plan = result.scalar_one_or_none()

    if plan:
        await handle_meal_ready_response(plan.id, True, parent.whatsapp_id, db)
        await db.commit()
    else:
        from app.services.whatsapp import send_text_message
        label = await _get_label(parent, db)
        await send_text_message(
            parent.whatsapp_id,
            "Abhi koi active meal plan nahi hai. 🙏",
            household_label=label,
        )


# ---------------------------------------------------------------------------
# Household-mode intent helpers
# ---------------------------------------------------------------------------

MEAL_QUERY_KEYWORDS = [
    "kya banega", "kya banau", "kya banaye", "kya banaun",
    "lunch", "dinner", "breakfast", "khana", "nashta",
    "aaj ka menu", "what to cook", "what should i make",
    "meal plan", "suggest meal", "kya pakaye", "kya khayenge",
]


def _might_be_meal_query(text: str) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in MEAL_QUERY_KEYWORDS)


async def _handle_meal_query(parent: Parent, text: str, db):
    """Route a meal query to the meal engine and notify the approver."""
    from app.services.meal_engine import suggest_meals
    from app.services.notification import notify_family_children
    from app.services.whatsapp import send_text_message

    label = await _get_label(parent, db)
    meal_type = _detect_meal_type(text)
    suggestions = await suggest_meals(parent.family_id, meal_type, db)

    if not suggestions.get("options"):
        await send_text_message(
            parent.whatsapp_id,
            "Abhi kuch suggestions nahi mil rahi. Thodi der mein try karte hain. 🙏",
            household_label=label,
        )
        return

    options = suggestions["options"]
    summary_lines = [f"🍽️ {parent.name} puch rahi hai: aaj {meal_type} mein kya banega?\n"]
    for i, opt in enumerate(options, 1):
        dishes = ", ".join(opt.get("dishes", []))
        time_str = f" ({opt.get('estimated_cook_time_mins', '?')} min)" if opt.get("estimated_cook_time_mins") else ""
        missing = opt.get("missing_ingredients", [])
        missing_str = ""
        if missing:
            missing_names = [m["name"] for m in missing]
            missing_str = f"\n   ⚠️ Missing: {', '.join(missing_names)}"
        summary_lines.append(f"{i}. {opt['name']}: {dishes}{time_str}{missing_str}")
        if opt.get("reason"):
            summary_lines.append(f"   💡 {opt['reason']}")

    await send_text_message(
        parent.whatsapp_id,
        "Sahab/Ma'am ko puch rahi hoon... ek minute. ⏳",
        household_label=label,
    )

    await notify_family_children(
        parent.family_id,
        "Meal Suggestion",
        "\n".join(summary_lines),
        data={"type": "meal_query", "options": suggestions["options"], "meal_type": meal_type, "cook_id": str(parent.id)},
        db=db,
    )


def _detect_meal_type(text: str) -> str:
    text_lower = text.lower()
    if any(kw in text_lower for kw in ("breakfast", "nashta", "subah")):
        return "breakfast"
    if any(kw in text_lower for kw in ("lunch", "dopahar", "khana")):
        return "lunch"
    if any(kw in text_lower for kw in ("dinner", "raat", "shaam")):
        return "dinner"
    from datetime import datetime
    hour = datetime.now(UTC).hour + 5  # IST approximation
    if hour < 10:
        return "breakfast"
    elif hour < 15:
        return "lunch"
    return "dinner"


async def _handle_absence(parent: Parent, text: str, db):
    """Record absence and notify the approver with replacement options."""
    from datetime import date as date_type

    from app.services.absence import build_replacement_card, parse_absence_date, record_absence
    from app.services.notification import notify_family_children
    from app.services.whatsapp import send_text_message

    label = await _get_label(parent, db)
    absence_date = parse_absence_date(text)
    absence = await record_absence(parent, reason=text[:255], db=db, absence_date=absence_date)
    await db.commit()

    card = build_replacement_card(parent, absence)
    role_label = parent.role.replace("_", " ").title()
    today = date_type.today()
    is_advance = absence_date > today
    days_until = (absence_date - today).days

    if is_advance:
        if days_until == 1:
            date_label = "kal"
        elif days_until == 2:
            date_label = "parso"
        else:
            date_label = f"{days_until} din baad ({absence_date.strftime('%d %b')})"

        await send_text_message(
            parent.whatsapp_id,
            f"Theek hai, {date_label} ki chutti note kar li hai. 👍\n"
            f"Sahab/Ma'am ko bata diya. Hum replacement dhundhte hain. 🙏",
            household_label=label,
        )

        msg_lines = [
            f"📅 {parent.name} ({role_label}) {date_label} nahi aa payenge.",
        ]
        if absence.reason:
            msg_lines.append(f"Reason: {absence.reason}")
        msg_lines.append(
            f"\nBimi will monitor {card['replacement_options'][0]['platform_name'] if card['replacement_options'] else 'platforms'} "
            f"and notify you when a slot is available."
        )

        await notify_family_children(
            parent.family_id,
            f"{role_label} Leave — {date_label}",
            "\n".join(msg_lines),
            data={"type": "advance_absence", "absence_card": card, "days_until": days_until},
            db=db,
        )
    else:
        await send_text_message(
            parent.whatsapp_id,
            "Theek hai, aap rest karo. 👍 Chutti note kar li, ghar walon ko bata diya. 🙏",
            household_label=label,
        )

        msg_lines = [
            f"⚠️ {parent.name} ({role_label}) aaj nahi aa payenge.",
        ]
        if absence.reason:
            msg_lines.append(f"Reason: {absence.reason}")

        if card["replacement_options"]:
            msg_lines.append("\nReplacement options available in the app.")

        await notify_family_children(
            parent.family_id,
            f"{role_label} Absent",
            "\n".join(msg_lines),
            data={
                "type": "absence",
                "absence_card": card,
            },
            db=db,
        )


# ---------------------------------------------------------------------------
# Standing instruction detection
# ---------------------------------------------------------------------------

INSTRUCTION_KEYWORDS_HI = [
    "roz", "har roz", "everyday", "daily",
    "hamesha", "always", "roz subah", "roz shaam",
    "cooking ke baad", "khana banane ke baad",
    "bheego ke", "soak", "dhona", "saaf karna", "clean",
    "banana hai", "rakhna hai", "karna hai", "yaad rakhna",
    "instruction", "rule", "standing",
]

INSTRUCTION_KEYWORDS_EN = [
    "every day", "every morning", "every evening", "daily",
    "always", "make sure", "remember to", "don't forget",
    "after cooking", "before cooking", "should always",
    "tell the cook", "ask cook to", "cook should",
    "maid should", "instruction for",
]


def _might_be_instruction(text: str) -> bool:
    """Check if a message is issuing a standing instruction."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in INSTRUCTION_KEYWORDS_HI + INSTRUCTION_KEYWORDS_EN)


async def _handle_instruction(parent: Parent, text: str, db):
    """Process a standing instruction from WhatsApp and confirm with user."""
    from app.services.instruction_engine import create_instruction, extract_instruction
    from app.services.notification import notify_family_children
    from app.services.whatsapp import send_reply_buttons

    label = await _get_label(parent, db)
    extracted = await extract_instruction(text, parent.family_id)

    instruction = await create_instruction(
        family_id=parent.family_id,
        created_by_type="parent",
        created_by_id=parent.id,
        raw_text=text,
        db=db,
        extracted=extracted,
    )
    await db.commit()

    instruction_text = extracted.get("instruction_text", text)
    rec = extracted.get("recurrence", {})
    rec_type = rec.get("type", "daily")
    time_str = rec.get("time_of_day", "")
    schedule = f"{rec_type}"
    if time_str:
        schedule += f" at {time_str}"

    await send_reply_buttons(
        parent.whatsapp_id,
        f"Standing instruction samajh gayi:\n\n"
        f"📋 {instruction_text}\n"
        f"⏰ Schedule: {schedule}\n"
        f"👤 For: {extracted.get('target_role', 'cook')}\n\n"
        f"Sahab/Ma'am ko bata diya. Roz yaad dilaongi! 👍",
        buttons=[
            {"id": f"inst_ok_{instruction.id}", "title": "✅ Theek hai"},
            {"id": f"inst_cancel_{instruction.id}", "title": "❌ Cancel karo"},
        ],
        household_label=label,
    )

    await notify_family_children(
        parent.family_id,
        "New Standing Instruction",
        f"{parent.name} added: \"{instruction_text}\" ({schedule})",
        data={"type": "new_instruction", "instruction_id": str(instruction.id)},
        db=db,
    )


async def _handle_late_arrival_eta(parent: Parent, text: str, db):
    """Parse the cook's ETA reply after they tapped 'Late hoongi'."""
    from app.services.attendance import (
        notify_parent_partial_deviation,
        parse_arrival_or_leave_time,
        record_late_arrival,
    )
    from app.services.whatsapp import send_text_message

    # Late arrivals are usually morning (cook normally arrives 8-10 AM
    # and slips by an hour or two). Default AM here.
    eta = parse_arrival_or_leave_time(text, default_pm=False)
    if eta is None:
        await send_text_message(
            parent.whatsapp_id,
            "Time samajh nahi aaya. Kya aap likh sakte hain (jaise '10 baje' ya '10:30 am')?",
        )
        # Re-stash so the next reply can still capture the ETA.
        from app.services.attendance import stash_pending_eta
        await stash_pending_eta(parent.whatsapp_id, str(parent.id))
        return

    await record_late_arrival(parent, eta, db, reason=text[:255])
    await db.commit()
    await notify_parent_partial_deviation(
        parent, deviation="late_arrival", deviation_time=eta, db=db, reason=text[:255],
    )
    await send_text_message(
        parent.whatsapp_id,
        f"Theek hai, {eta.strftime('%I:%M %p').lstrip('0')} tak aa jaiye. "
        "Sahab/Ma'am ko bata diya. 🙏",
    )


async def _handle_late_arrival_text(parent: Parent, text: str, db):
    """Cook proactively sent 'late hoongi' (without the button flow)."""
    from app.services.attendance import (
        notify_parent_partial_deviation,
        parse_arrival_or_leave_time,
        record_late_arrival,
    )
    from app.services.whatsapp import send_text_message

    eta = parse_arrival_or_leave_time(text, default_pm=False)
    if eta is None:
        # Ask for the time explicitly via the same pending-ETA flow.
        from app.services.attendance import stash_pending_eta
        await stash_pending_eta(parent.whatsapp_id, str(parent.id))
        await send_text_message(
            parent.whatsapp_id,
            "Theek hai. Kitne baje aaogi?",
        )
        return

    await record_late_arrival(parent, eta, db, reason=text[:255])
    await db.commit()
    await notify_parent_partial_deviation(
        parent, deviation="late_arrival", deviation_time=eta, db=db, reason=text[:255],
    )
    await send_text_message(
        parent.whatsapp_id,
        f"Theek hai, {eta.strftime('%I:%M %p').lstrip('0')} tak aa jaiye. 🙏",
    )


async def _handle_early_leave(parent: Parent, text: str, db):
    """Cook said something like 'doctor jaana hai, 2 baje nikal jaungi'."""
    from app.services.attendance import (
        notify_parent_partial_deviation,
        parse_arrival_or_leave_time,
        record_early_leave,
    )
    from app.services.whatsapp import send_text_message

    # Early-leave times are almost always afternoon/evening.
    leave_time = parse_arrival_or_leave_time(text, default_pm=True)
    if leave_time is None:
        await send_text_message(
            parent.whatsapp_id,
            "Theek hai, kitne baje nikalengi? Time bhej dijiye.",
        )
        # No pending state for this branch — cook can re-state proactively.
        return

    await record_early_leave(parent, leave_time, db, reason=text[:255])
    await db.commit()
    await notify_parent_partial_deviation(
        parent, deviation="early_leave", deviation_time=leave_time, db=db, reason=text[:255],
    )
    await send_text_message(
        parent.whatsapp_id,
        f"Samajh gayi, {leave_time.strftime('%I:%M %p').lstrip('0')} tak khana ban jana chahiye. "
        "Sahab/Ma'am ko bata diya. 🙏",
    )


async def _handle_feedback(parent: Parent, text: str, db):
    """Process behavioral feedback about Bimi."""
    from app.services.feedback_metabolism import extract_feedback, metabolize_feedback
    from app.services.whatsapp import send_text_message

    label = await _get_label(parent, db)
    feedback = await extract_feedback(text)

    if feedback.get("feedback_type") == "not_feedback":
        return

    log = await metabolize_feedback(
        family_id=parent.family_id,
        person_type="parent",
        person_id=parent.id,
        feedback=feedback,
        raw_text=text,
        db=db,
    )
    await db.commit()

    interpretation = feedback.get("raw_interpretation", "your feedback")
    auto_applied = log.auto_applied if log else False

    if auto_applied:
        await send_text_message(
            parent.whatsapp_id,
            f"Samajh gayi! 🙏\n\n"
            f"Aapne kaha: {interpretation}\n\n"
            f"Maine abhi se change kar diya hai. Agar koi problem ho toh batayein.",
            household_label=label,
        )
    else:
        await send_text_message(
            parent.whatsapp_id,
            f"Samajh gayi! 🙏\n\n"
            f"Aapne kaha: {interpretation}\n\n"
            f"Sahab/Ma'am ko bata diya — woh decide karenge.",
            household_label=label,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _lookup_parent(wa_id: str, db) -> Parent | None:
    """
    Look up a Parent by WhatsApp ID. If the phone appears in multiple families
    (cook working in several homes) but no SharedCook record exists yet, return
    the first match so the legacy flow still works.
    """
    result = await db.execute(
        select(Parent).where(Parent.whatsapp_id == wa_id).limit(1)
    )
    return result.scalar_one_or_none()
