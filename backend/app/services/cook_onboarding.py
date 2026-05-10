"""WhatsApp-native cook onboarding.

Slice 5 of the WhatsApp coordination plan. When a household adds a
cook in the app (a Parent row with `role='cook'` and a `whatsapp_id`
gets inserted), the API surface should call `send_onboarding_card` to
greet the cook on WhatsApp:

    Namaste Geeta ji! 🙏
    Aap {family_name} ke ghar ki cook hain?
    [✅ Haan]   [❌ Galat number]

The cook's tap is handled by `_handle_onboarding_button` in the
webhook router:
  - Haan → set `onboarded_at = now()`; the cook is fully active.
  - Galat → set `is_active = false`; future briefs/pings skip them
    and the family's primary parent gets a notification so they can
    fix the number.

Per spec we deliberately skip OTP — cooks rarely open SMS reliably,
and the WhatsApp confirmation tap gives equivalent identity proof
(Meta's signed webhook plus the cook actively pressing the button).
"""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.family import Family, Parent

logger = logging.getLogger("bimi.cook_onboarding")


async def send_onboarding_card(parent: Parent, family: Family) -> None:
    """Send the welcome confirmation card to a freshly-added cook.

    Caller must commit the parent row first; this only sends the
    WhatsApp message and does not touch the DB.
    """
    from app.services.whatsapp import send_reply_buttons

    role_label = (parent.role or "cook").replace("_", " ")
    body = (
        f"Namaste {parent.name} ji! 🙏\n\n"
        f"Aap {family.name} ke ghar ki {role_label} hain?\n"
        f"Confirm karein:"
    )
    await send_reply_buttons(
        to=parent.whatsapp_id,
        body=body,
        buttons=[
            {"id": f"onboard_yes_{parent.id}", "title": "✅ Haan"},
            {"id": f"onboard_no_{parent.id}", "title": "❌ Galat number"},
        ],
        footer="Bimi",
    )


async def trigger_cook_onboarding(
    parent: Parent, db: AsyncSession,
) -> bool:
    """Auto-fire the welcome card when a new cook Parent is created.

    Idempotent and gated — call this from any cook-creation surface
    (register_cook, add_parent, future flows) without worrying about
    duplicate sends. Returns True if a card was sent, False otherwise.

    Skip rules (in priority order):
      1. Feature flag `settings.cook_onboarding_enabled` is False.
      2. `parent.role != 'cook'` — only cooks get this card; future
         work may extend to maids/drivers but they aren't covered yet.
      3. `parent.is_active is False` — parent is deactivated; sending
         a welcome to a 'galat number' contact would be confusing.
      4. `parent.onboarded_at is not None` — already confirmed once;
         a second card would be noise.
      5. `parent.whatsapp_id` is empty — nothing to send to.

    Best-effort: WhatsApp send failures are logged but never raised.
    The cook-creation API must complete even if Meta is degraded.
    """
    from app.config import settings

    if not settings.cook_onboarding_enabled:
        logger.info(
            "cook_onboarding skipped (flag off) for parent %s", parent.id,
        )
        return False
    if (parent.role or "").lower() != "cook":
        return False
    if parent.is_active is False:
        return False
    if parent.onboarded_at is not None:
        return False
    if not parent.whatsapp_id:
        logger.warning(
            "cook_onboarding skipped: parent %s has no whatsapp_id", parent.id,
        )
        return False

    family = await db.get(Family, parent.family_id)
    if family is None:
        logger.warning(
            "cook_onboarding skipped: family %s missing for parent %s",
            parent.family_id, parent.id,
        )
        return False

    try:
        await send_onboarding_card(parent, family)
        logger.info(
            "cook_onboarding card sent: parent=%s wa=%s family=%s",
            parent.id, parent.whatsapp_id, family.id,
        )
        return True
    except Exception:  # noqa: BLE001 — onboarding failure must never 5xx the API
        logger.exception(
            "cook_onboarding send failed for parent %s — recoverable via "
            "POST /api/households/cooks/{parent_id}/resend-onboarding",
            parent.id,
        )
        return False


async def confirm_onboarding(parent: Parent, db: AsyncSession) -> None:
    """Mark the cook as onboarded and welcome them."""
    from app.services.whatsapp import send_text_message

    if parent.onboarded_at is None:
        parent.onboarded_at = datetime.now(UTC)
    parent.is_active = True
    await db.flush()

    await send_text_message(
        parent.whatsapp_id,
        f"Bahut badhiya {parent.name} ji! 🙏\n"
        "Ab main aapki seva mein hoon. Roz subah aapko khane ka plan bhejungi, "
        "aur agar koi sawaal ho toh kabhi bhi voice note bhej dijiye.",
    )


async def reject_onboarding(parent: Parent, db: AsyncSession) -> None:
    """Cook said 'Galat number' — deactivate row and notify the primary parent."""
    from app.services.notification import notify_family_children
    from app.services.whatsapp import send_text_message

    parent.is_active = False
    await db.flush()

    await send_text_message(
        parent.whatsapp_id,
        "Maaf kijiye! 🙏 Hum aapko aur message nahi karenge. "
        "Agar yeh galti se hua hai toh ghar walon ko bata dijiye.",
    )

    await notify_family_children(
        parent.family_id,
        f"{(parent.role or 'Cook').title()} number issue",
        f"⚠️ {parent.name} ne 'Galat number' bola. "
        f"Phone {parent.phone} pe message nahi pahunch raha.\n\n"
        "Number check karke app mein update karein.",
        data={
            "type": "cook_onboarding_rejected",
            "parent_id": str(parent.id),
            "phone": parent.phone,
        },
        db=db,
    )


async def maybe_handle_onboarding_button(
    btn_id: str, db: AsyncSession,
) -> bool:
    """Route onboard_yes / onboard_no buttons. Returns True if handled.

    Routed BEFORE the generic webhook button dispatcher so the cook
    confirmation flow gets first crack at the tap.
    """
    if btn_id.startswith("onboard_yes_"):
        parent_id_str = btn_id[len("onboard_yes_"):]
        parent = await _resolve_parent(parent_id_str, db)
        if parent is None:
            return True
        await confirm_onboarding(parent, db)
        await db.commit()
        return True

    if btn_id.startswith("onboard_no_"):
        parent_id_str = btn_id[len("onboard_no_"):]
        parent = await _resolve_parent(parent_id_str, db)
        if parent is None:
            return True
        await reject_onboarding(parent, db)
        await db.commit()
        return True

    return False


async def _resolve_parent(parent_id_str: str, db: AsyncSession) -> Parent | None:
    try:
        parent_id = uuid.UUID(parent_id_str)
    except ValueError:
        logger.warning("Invalid parent_id in onboarding button: %s", parent_id_str)
        return None
    res = await db.execute(select(Parent).where(Parent.id == parent_id).limit(1))
    return res.scalar_one_or_none()
