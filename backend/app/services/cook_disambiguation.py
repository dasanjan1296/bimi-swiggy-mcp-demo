"""
Cook Disambiguation — WhatsApp interactive pickers for multi-household cooks.

Sends button/list messages when the context resolver cannot determine which
household a cook's message belongs to, and handles broadcast intents like
absence notifications that affect multiple homes.
"""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.shared_cook import SharedCook
from app.services.cook_context import get_active_households
from app.services.whatsapp import send_list_message, send_reply_buttons, send_text_message

logger = logging.getLogger(__name__)


async def send_household_picker(
    cook: SharedCook,
    db: AsyncSession,
    prompt: str | None = None,
) -> None:
    """
    Send interactive buttons letting the cook choose which household.
    WhatsApp allows at most 3 reply buttons, so if >3 households we use a list.
    """
    active = await get_active_households(cook, db)
    if not active:
        return

    prompt_text = prompt or "Kaunse ghar ke liye?"

    if len(active) <= 3:
        buttons = [
            {
                "id": f"cook_switch_{hh.family_id}",
                "title": _short_label(hh.household_label),
            }
            for hh in active
        ]
        await send_reply_buttons(
            to=cook.whatsapp_id,
            body=prompt_text,
            buttons=buttons,
        )
    else:
        rows = [
            {
                "id": f"cook_switch_{hh.family_id}",
                "title": _short_label(hh.household_label),
                "description": "",
            }
            for hh in active
        ]
        await send_list_message(
            to=cook.whatsapp_id,
            body=prompt_text,
            button_text="Ghar chunein",
            sections=[{"title": "Aapke ghar", "rows": rows}],
        )


async def send_absence_picker(
    cook: SharedCook,
    db: AsyncSession,
    date_text: str = "kal",
) -> None:
    """
    When a cook reports absence, ask which household(s) she won't visit.
    Includes a "Sab ghar" (all homes) option.
    """
    active = await get_active_households(cook, db)
    if not active:
        return

    if len(active) == 1:
        return

    buttons: list[dict[str, str]] = [
        {"id": "cook_broadcast_absence_all", "title": "Sab ghar"},
    ]

    for hh in active[:2]:
        buttons.append({
            "id": f"cook_broadcast_absence_{hh.family_id}",
            "title": _short_label(hh.household_label),
        })

    await send_reply_buttons(
        to=cook.whatsapp_id,
        body=f"{date_text.capitalize()} kaunse ghar nahi jaogi?",
        buttons=buttons,
    )


async def handle_absence_broadcast(
    cook: SharedCook,
    btn_id: str,
    original_text: str,
    db: AsyncSession,
) -> list[uuid.UUID]:
    """
    Process absence broadcast button tap. Returns list of family_ids affected.
    The caller should then record absences for each returned family.
    """
    active = await get_active_households(cook, db)
    if not active:
        return []

    if btn_id == "cook_broadcast_absence_all":
        family_ids = [hh.family_id for hh in active]
        labels = [hh.household_label for hh in active]
        await send_text_message(
            cook.whatsapp_id,
            f"Theek hai, sab gharon ko bata diya: {', '.join(labels)} 👍\n"
            f"Hum replacement dhundhte hain. 🙏",
        )
        return family_ids

    if btn_id.startswith("cook_broadcast_absence_"):
        family_id_str = btn_id.replace("cook_broadcast_absence_", "")
        try:
            family_id = uuid.UUID(family_id_str)
        except ValueError:
            return []
        hh = next((h for h in active if h.family_id == family_id), None)
        if hh:
            await send_text_message(
                cook.whatsapp_id,
                f"Theek hai, {hh.household_label} ko bata diya. 👍\n"
                f"Hum replacement dhundhte hain. 🙏",
            )
            return [family_id]

    return []


def _short_label(label: str) -> str:
    """Truncate label to fit WhatsApp button title limit (20 chars)."""
    return label[:20] if len(label) > 20 else label
