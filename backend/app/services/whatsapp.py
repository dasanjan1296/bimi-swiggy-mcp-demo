"""
WhatsApp Business Cloud API integration.

Supports:
- Downloading media (voice notes, images)
- Sending plain text messages
- Sending interactive reply-button messages (up to 3 buttons)
- Sending interactive list-picker messages (up to 10 rows)
- Hindi/English bilingual message formatting
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

BASE_URL = "https://graph.facebook.com/v21.0"


# ---------------------------------------------------------------------------
# Media download
# ---------------------------------------------------------------------------

# Loop 15: cap media downloads at 20 MB. Meta's documented max for
# audio/video is 16 MB; we add 4 MB headroom. Without this cap, a buggy
# or attacker-controlled redirect URL could OOM the worker by serving
# GBs of bytes — `media_resp.content` reads the entire body into memory.
_MEDIA_MAX_BYTES = 20 * 1024 * 1024


async def download_media(media_id: str) -> bytes:
    """Download any WhatsApp media (voice note, image, document) by ID.

    Routes through the adapter so tests + dev pick up the
    FakeWhatsAppAdapter automatically. The size cap (Loop 15) is
    enforced in the production adapter.
    """
    from app.adapters import get_whatsapp_adapter
    adapter = get_whatsapp_adapter()
    return await adapter.download_media(media_id)


# Keep the old name as an alias
download_voice_note = download_media


# ---------------------------------------------------------------------------
# Outbound messaging — low-level
# ---------------------------------------------------------------------------

async def _send_message(payload: dict) -> dict:
    """Send any message payload via the WhatsApp adapter.

    Multimodal validation loop fix: the helper now routes through
    `get_whatsapp_adapter()` so:
      - In production: `CloudApiWhatsAppAdapter` calls Meta directly.
      - In tests / dev: `FakeWhatsAppAdapter` records the message and
        returns a deterministic id, so confirmation flows can be
        end-to-end-asserted without a live WhatsApp token.

    The 429 retry behaviour (Loop 13) lives inside the production
    adapter via httpx error mapping; for the Fake, sends are always
    successful.
    """
    from app.adapters import get_whatsapp_adapter

    adapter = get_whatsapp_adapter()
    result = await adapter.send_message(payload)
    return {"message_id": result.message_id, "raw": result.raw}


async def send_text_message(to: str, text: str, household_label: str | None = None) -> dict:
    """Send a plain text message, optionally prefixed with a household tag."""
    if household_label:
        text = f"[🏠 {household_label}] {text}"
    return await _send_message({
        "to": to,
        "type": "text",
        "text": {"body": text},
    })


async def send_reply_buttons(
    to: str,
    body: str,
    buttons: list[dict[str, str]],
    header: str | None = None,
    footer: str | None = None,
    household_label: str | None = None,
) -> dict:
    """
    Send an interactive message with up to 3 reply buttons.

    buttons: [{"id": "confirm_yes", "title": "✅ Sahi hai"}]
    """
    if household_label:
        body = f"[🏠 {household_label}] {body}"
    action_buttons = [
        {"type": "reply", "reply": {"id": btn["id"], "title": btn["title"][:20]}}
        for btn in buttons[:3]
    ]
    interactive: dict[str, Any] = {
        "type": "button",
        "body": {"text": body},
        "action": {"buttons": action_buttons},
    }
    if header:
        interactive["header"] = {"type": "text", "text": header}
    if footer:
        interactive["footer"] = {"text": footer}

    return await _send_message({
        "to": to,
        "type": "interactive",
        "interactive": interactive,
    })


async def send_list_message(
    to: str,
    body: str,
    button_text: str,
    sections: list[dict],
    header: str | None = None,
    footer: str | None = None,
) -> dict:
    """
    Send an interactive list picker message.

    sections: [
        {
            "title": "Section Title",
            "rows": [
                {"id": "row_1", "title": "Row Title", "description": "Optional desc"}
            ]
        }
    ]
    """
    interactive: dict[str, Any] = {
        "type": "list",
        "body": {"text": body},
        "action": {
            "button": button_text[:20],
            "sections": sections,
        },
    }
    if header:
        interactive["header"] = {"type": "text", "text": header}
    if footer:
        interactive["footer"] = {"text": footer}

    return await _send_message({
        "to": to,
        "type": "interactive",
        "interactive": interactive,
    })


# ---------------------------------------------------------------------------
# Adaptive message composition (communication profile aware)
# ---------------------------------------------------------------------------

async def get_comm_profile_for_parent(parent_id, family_id=None):
    """Fetch communication profile for a parent (returns None if not found)."""
    try:
        from app.db import async_session
        from app.services.comm_adapter import get_or_create_profile
        async with async_session() as db:
            return await get_or_create_profile(family_id, "parent", parent_id, db)
    except Exception:
        return None


async def send_adaptive_text(to: str, text_hi: str, text_en: str, parent_id=None, family_id=None) -> dict:
    """Send a text message adapted to the person's language preference."""
    profile = await get_comm_profile_for_parent(parent_id, family_id) if parent_id else None
    if profile and profile.is_english_dominant:
        return await send_text_message(to, text_en)
    elif profile and profile.is_hindi_dominant:
        return await send_text_message(to, text_hi)
    return await send_text_message(to, text_hi)


# ---------------------------------------------------------------------------
# Rich message builders (Hindi + English bilingual)
# ---------------------------------------------------------------------------

def format_items_for_confirmation(items: list[dict]) -> str:
    """Build the item list shown in the confirmation message."""
    lines = []
    for i, item in enumerate(items, 1):
        brand = f" ({item['brand']})" if item.get("brand") else ""
        qty = item.get("quantity", 1)
        unit = item.get("unit", "pcs")
        lines.append(f"{i}. {item['name']}{brand} — {qty} {unit}")
    return "\n".join(lines)


async def send_high_confidence_confirmation(
    to: str, items: list[dict], parent_id=None, family_id=None,
) -> dict:
    """
    High confidence: show items with ✅/❌/➕ buttons.
    Adapts to communication profile — bulk confirmation for high-accuracy parents.
    """
    profile = await get_comm_profile_for_parent(parent_id, family_id) if parent_id else None

    if profile and profile.should_batch_confirmations and len(items) > 3:
        item_names = ", ".join(item["name"] for item in items)
        body = f"Maine samjha: {item_names} ({len(items)} items). Sahi hai?"
        return await send_reply_buttons(
            to=to,
            body=body,
            buttons=[
                {"id": "confirm_yes", "title": "✅ Haan, sahi hai"},
                {"id": "confirm_no", "title": "❌ Nahi, galat hai"},
                {"id": "confirm_add", "title": "➕ Aur add karo"},
            ],
            footer="Bimi",
        )

    item_list = format_items_for_confirmation(items)
    body = f"Maine samjha:\n\n{item_list}\n\nKya yeh sahi hai?"

    return await send_reply_buttons(
        to=to,
        body=body,
        buttons=[
            {"id": "confirm_yes", "title": "✅ Haan, sahi hai"},
            {"id": "confirm_no", "title": "❌ Nahi, galat hai"},
            {"id": "confirm_add", "title": "➕ Aur add karo"},
        ],
        footer="Bimi",
    )


async def send_medium_confidence_confirmation(
    to: str, items: list[dict]
) -> dict:
    """
    Medium confidence: show items with a softer prompt.
    Asks Mom to check carefully and offers text/photo as alternatives.
    """
    item_list = format_items_for_confirmation(items)
    body = (
        f"Mujhe lagta hai aapne yeh manga:\n\n{item_list}\n\n"
        "Kya yeh sahi hai? Agar galat hai toh aap text mein likh sakte hain ya photo bhej sakte hain."
    )

    return await send_reply_buttons(
        to=to,
        body=body,
        buttons=[
            {"id": "confirm_yes", "title": "✅ Haan, sahi hai"},
            {"id": "confirm_no", "title": "❌ Galat hai"},
            {"id": "confirm_retry", "title": "🔄 Dobara bolun"},
        ],
        footer="Bimi",
    )


async def send_low_confidence_fallback(
    to: str,
    reorder_items: list[dict] | None = None,
    *,
    best_guess: str | None = None,
) -> dict:
    """
    Low confidence: couldn't fully understand the voice note.

    Per the multimodal validation report (F3), if we have ANY transcript
    we offer a best-guess interpretation with ✅/❌/✏️ buttons. This
    keeps the conversation alive instead of flat-failing with a generic
    "samajh nahi aaya". Only when we have nothing usable do we fall
    back to the asks-for-text-or-photo path.

    `best_guess` should be the cleaned transcript or the system's best
    natural-language reading of it.
    """
    if best_guess and best_guess.strip():
        body = (
            "Samajh nahi aaya thik se. 🙏\n\n"
            f"Kya aap yeh kehna chah rahe the:\n*\"{best_guess.strip()}\"*?"
        )
        return await send_reply_buttons(
            to=to,
            body=body,
            buttons=[
                {"id": "lowconf_yes", "title": "✅ Haan, yahi"},
                {"id": "lowconf_no", "title": "❌ Nahi, dobara"},
                {"id": "lowconf_text", "title": "✏️ Text bhejun"},
            ],
            footer="Bimi",
        )

    if reorder_items:
        rows = [
            {
                "id": f"reorder_{i}",
                "title": item["item_name"][:24],
                "description": f"{item.get('brand', '')} {item.get('quantity', '')} {item.get('unit', '')}".strip()[:72],
            }
            for i, item in enumerate(reorder_items[:10])
        ]
        return await send_list_message(
            to=to,
            body=(
                "Maaf kijiye, aapki awaaz clearly nahi sun payi. 🙏\n\n"
                "Aap yeh kar sakte hain:\n"
                "1. Text mein likh kar bhejein\n"
                "2. Item ki photo bhejein\n"
                "3. Neeche apne regular items mein se chunein"
            ),
            button_text="Regular items",
            sections=[{"title": "Aapke regular items", "rows": rows}],
            footer="Bimi",
        )
    else:
        return await send_text_message(
            to,
            "Maaf kijiye, mujhe samajh nahi aaya. 🙏\n\n"
            "Kya aap text mein likh sakte hain kya chahiye? "
            "Ya item ki photo bhej dijiye.",
        )


async def send_disambiguation_list(
    to: str,
    item_name: str,
    alternatives: list[dict[str, str]],
) -> dict:
    """
    When we're unsure about a specific item, show options as a list.
    E.g., "Which atta?" → [Aashirvaad 5kg, Fortune 5kg, Pillsbury 5kg]
    """
    rows = [
        {
            "id": f"disambig_{i}",
            "title": alt["name"][:24],
            "description": alt.get("detail", "")[:72],
        }
        for i, alt in enumerate(alternatives[:10])
    ]
    return await send_list_message(
        to=to,
        body=f'"{item_name}" — aapko kaun sa chahiye?',
        button_text="Choose item",
        sections=[{"title": "Options", "rows": rows}],
        footer="Bimi",
    )


async def send_per_item_correction(
    to: str,
    item: dict,
    item_index: int,
) -> dict:
    """Ask about a specific item that might be wrong."""
    brand = f" ({item['brand']})" if item.get("brand") else ""
    body = (
        f"Item #{item_index + 1}: {item['name']}{brand} — {item.get('quantity', 1)} {item.get('unit', 'pcs')}\n\n"
        "Kya yeh sahi hai?"
    )
    return await send_reply_buttons(
        to=to,
        body=body,
        buttons=[
            {"id": f"item_ok_{item_index}", "title": "✅ Sahi hai"},
            {"id": f"item_wrong_{item_index}", "title": "❌ Galat hai"},
            {"id": f"item_remove_{item_index}", "title": "🗑 Hatao"},
        ],
        footer=f"Item {item_index + 1} of correction",
    )


async def send_cart_summary(
    to: str,
    items: list[dict],
    cart_total: float | None = None,
) -> dict:
    """Send a summary of items added to cart, with option to add more or send to child."""
    item_list = format_items_for_confirmation(items)
    total_str = f"\n\n💰 Estimated total: ₹{cart_total:.0f}" if cart_total else ""
    body = f"Aapke cart mein abhi:\n\n{item_list}{total_str}"

    return await send_reply_buttons(
        to=to,
        body=body,
        buttons=[
            {"id": "cart_send", "title": "📤 Beta ko bhejo"},
            {"id": "cart_add", "title": "➕ Aur add karo"},
            {"id": "cart_clear", "title": "🗑 Sab hatao"},
        ],
        footer="Bimi",
    )


def format_order_confirmation(items: list[dict], platform: str) -> str:
    """Confirmation sent to parent after child approves."""
    count = len(items)
    item_word = "item" if count == 1 else "items"
    return (
        f"Beta ne aapke {count} {item_word} order kar diye! ✅\n"
        f"Coming via {platform}.\n"
        "Delivery update aata rahega. 🙂"
    )


# ---------------------------------------------------------------------------
# Delivery tracking messages
# ---------------------------------------------------------------------------

async def send_order_placed(
    to: str,
    item_count: int,
    platform: str,
    delivery_eta: str | None = None,
    delivery_slot: str | None = None,
    tracking_link: str | None = None,
) -> dict:
    """Sent to Mom when order is confirmed on the platform."""
    platform_name = "Swiggy Instamart" if "instamart" in platform else "Swiggy Food" if "food" in platform else "Swiggy"
    body = f"🛒 Order ho gaya via {platform_name}! {item_count} items\n\n"
    body += f"*Platform:* {platform_name} (powered by Swiggy)\n"

    if delivery_slot:
        body += f"*Delivery:* {delivery_slot}\n"
    elif delivery_eta:
        body += f"*Delivery:* {delivery_eta}\n"

    if tracking_link:
        body += f"\n📍 Track karo: {tracking_link}"

    body += "\n\nJab delivery aayegi tab bata denge! 😊"

    return await send_text_message(to, body)


async def send_out_for_delivery(
    to: str,
    eta_minutes: int | None = None,
    tracking_link: str | None = None,
) -> dict:
    """Sent when order is out for delivery."""
    body = "🚚 Aapka order delivery ke liye nikal gaya!"
    if eta_minutes:
        body += f"\n\n⏱ {eta_minutes} minute mein pahunch jayega."
    if tracking_link:
        body += f"\n\n📍 Track karo: {tracking_link}"
    return await send_text_message(to, body)


async def send_arriving_soon(to: str, minutes: int = 10) -> dict:
    """Sent when delivery is almost there."""
    return await send_text_message(
        to,
        f"📦 Aapka order bas {minutes} minute mein aa raha hai!\n\n"
        "Darwaza pe delivery boy aayega. 🏠"
    )


async def send_delivered(to: str, item_count: int) -> dict:
    """Sent after delivery is completed."""
    return await send_reply_buttons(
        to=to,
        body=f"✅ Aapka order deliver ho gaya! {item_count} items.\n\nSab kuch sahi mila?",
        buttons=[
            {"id": "delivery_ok", "title": "👍 Haan, sab sahi"},
            {"id": "delivery_issue", "title": "❌ Kuch problem hai"},
        ],
        footer="Bimi",
    )


async def send_delivery_scheduled(
    to: str,
    item_count: int,
    platform: str,
    slot: str,
) -> dict:
    """Sent when delivery is scheduled for a future slot."""
    platform_name = "Swiggy Instamart" if "instamart" in platform else "Swiggy Food" if "food" in platform else "Swiggy"
    return await send_text_message(
        to,
        f"📅 Order scheduled!\n\n"
        f"{item_count} items via {platform_name} (powered by Swiggy)\n"
        f"*Delivery:* {slot}\n\n"
        "Delivery se pehle reminder aayega. 😊"
    )


async def send_delivery_reminder(to: str, slot: str) -> dict:
    """Reminder before scheduled delivery."""
    return await send_text_message(
        to,
        f"⏰ Reminder: Aapka grocery order aaj deliver hoga!\n\n"
        f"*Slot:* {slot}\n\n"
        "Ghar pe rehiye. 🏠"
    )


# Ride-specific message builders removed — rides are out of scope.
