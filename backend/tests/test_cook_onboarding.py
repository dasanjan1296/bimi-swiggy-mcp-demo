"""WhatsApp-native cook onboarding — Slice 5 of the WhatsApp coordination plan.

Covers:
  - send_onboarding_card delivers a 2-button welcome to the cook
  - 'Haan' confirms onboarding (sets `onboarded_at`, keeps `is_active`)
  - 'Galat number' deactivates and notifies the family approvers
  - The button-id router handles unknown/garbage IDs gracefully
  - End-to-end auto-trigger from POST /api/parents (role='cook')
  - End-to-end auto-trigger from POST /api/households/register-cook
  - Feature-flag gate (cook_onboarding_enabled=False suppresses sends)
  - Idempotency (already-onboarded cook does not get re-greeted)
  - Manual resend endpoint for ops
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.models.family import Family, Parent
from app.services.cook_onboarding import (
    confirm_onboarding,
    maybe_handle_onboarding_button,
    reject_onboarding,
    send_onboarding_card,
    trigger_cook_onboarding,
)


async def _make_cook(db, family_id, *, phone="+919900555501", name="Geeta"):
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


@pytest.mark.asyncio
async def test_send_onboarding_card_emits_two_buttons(
    db, seed_family, fake_whatsapp,
):
    cook = await _make_cook(db, seed_family["family_id"])
    family = await db.get(Family, seed_family["family_id"])
    fake_whatsapp.reset()

    await send_onboarding_card(cook, family)

    sent = fake_whatsapp.messages_to(cook.whatsapp_id)
    assert len(sent) == 1
    payload = sent[0].payload
    assert payload["type"] == "interactive"
    button_ids = [
        b["reply"]["id"] for b in payload["interactive"]["action"]["buttons"]
    ]
    assert button_ids == [f"onboard_yes_{cook.id}", f"onboard_no_{cook.id}"]


@pytest.mark.asyncio
async def test_confirm_onboarding_sets_onboarded_at(db, seed_family):
    cook = await _make_cook(db, seed_family["family_id"])
    assert cook.onboarded_at is None

    await confirm_onboarding(cook, db)

    assert cook.onboarded_at is not None
    assert cook.is_active is True


@pytest.mark.asyncio
async def test_reject_onboarding_deactivates_and_notifies(
    db, seed_family, fake_whatsapp,
):
    cook = await _make_cook(db, seed_family["family_id"])
    fake_whatsapp.reset()

    await reject_onboarding(cook, db)

    assert cook.is_active is False
    # Cook receives the apology
    cook_msgs = fake_whatsapp.messages_to(cook.whatsapp_id)
    assert any("Maaf kijiye" in m.payload.get("text", {}).get("body", "") for m in cook_msgs)


@pytest.mark.asyncio
async def test_button_router_handles_yes(db, seed_family):
    cook = await _make_cook(db, seed_family["family_id"])
    handled = await maybe_handle_onboarding_button(
        f"onboard_yes_{cook.id}", db,
    )
    assert handled is True
    await db.refresh(cook)
    assert cook.onboarded_at is not None


@pytest.mark.asyncio
async def test_button_router_handles_no(db, seed_family):
    cook = await _make_cook(db, seed_family["family_id"])
    handled = await maybe_handle_onboarding_button(
        f"onboard_no_{cook.id}", db,
    )
    assert handled is True
    await db.refresh(cook)
    assert cook.is_active is False


@pytest.mark.asyncio
async def test_button_router_returns_false_for_unrelated_button(db):
    handled = await maybe_handle_onboarding_button("confirm_yes", db)
    assert handled is False


@pytest.mark.asyncio
async def test_button_router_swallows_unknown_parent_id(db):
    """A stale button (cook row deleted between send + tap) must not 500."""
    ghost = uuid.uuid4()
    handled = await maybe_handle_onboarding_button(f"onboard_yes_{ghost}", db)
    # Returns True because the prefix matched — we own the routing for it,
    # we just have nothing to do.
    assert handled is True


@pytest.mark.asyncio
async def test_button_router_swallows_garbage_uuid(db):
    handled = await maybe_handle_onboarding_button("onboard_yes_not-a-uuid", db)
    assert handled is True  # owned + ignored


# ---------------------------------------------------------------------------
# trigger_cook_onboarding — gating rules
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_skipped_when_role_is_not_cook(
    db, seed_family, fake_whatsapp,
):
    p = Parent(
        family_id=seed_family["family_id"],
        name="Mom",
        phone="+919900666601",
        whatsapp_id="919900666601",
        role="parent",
        language="hi",
    )
    db.add(p)
    await db.flush()
    fake_whatsapp.reset()

    sent = await trigger_cook_onboarding(p, db)
    assert sent is False
    assert fake_whatsapp.messages_to(p.whatsapp_id) == []


@pytest.mark.asyncio
async def test_trigger_skipped_when_already_onboarded(
    db, seed_family, fake_whatsapp,
):
    p = await _make_cook(db, seed_family["family_id"], phone="+919900666602")
    p.onboarded_at = datetime.now(UTC)
    await db.flush()
    fake_whatsapp.reset()

    sent = await trigger_cook_onboarding(p, db)
    assert sent is False


@pytest.mark.asyncio
async def test_trigger_skipped_when_inactive(db, seed_family, fake_whatsapp):
    p = await _make_cook(db, seed_family["family_id"], phone="+919900666603")
    p.is_active = False
    await db.flush()
    fake_whatsapp.reset()

    sent = await trigger_cook_onboarding(p, db)
    assert sent is False


@pytest.mark.asyncio
async def test_trigger_skipped_when_flag_off(
    db, seed_family, fake_whatsapp, monkeypatch,
):
    from app.config import settings
    monkeypatch.setattr(settings, "cook_onboarding_enabled", False)

    p = await _make_cook(db, seed_family["family_id"], phone="+919900666604")
    fake_whatsapp.reset()

    sent = await trigger_cook_onboarding(p, db)
    assert sent is False
    assert fake_whatsapp.messages_to(p.whatsapp_id) == []


@pytest.mark.asyncio
async def test_trigger_skipped_when_no_whatsapp_id(
    db, seed_family, fake_whatsapp,
):
    p = Parent(
        family_id=seed_family["family_id"],
        name="Anonymous",
        phone="+919900666605",
        whatsapp_id="",
        role="cook",
        language="hi",
    )
    db.add(p)
    await db.flush()
    fake_whatsapp.reset()

    sent = await trigger_cook_onboarding(p, db)
    assert sent is False


@pytest.mark.asyncio
async def test_trigger_swallows_send_failures(
    db, seed_family, monkeypatch,
):
    """A WhatsApp send error must not propagate (would 5xx the cook-create API)."""
    p = await _make_cook(db, seed_family["family_id"], phone="+919900666606")

    async def boom(*args, **kwargs):
        raise RuntimeError("WhatsApp degraded")

    monkeypatch.setattr(
        "app.services.cook_onboarding.send_onboarding_card", boom,
    )

    sent = await trigger_cook_onboarding(p, db)
    assert sent is False  # logged, not raised


# ---------------------------------------------------------------------------
# End-to-end via FE-facing API endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_parents_with_role_cook_fires_card(
    client, db, seed_family, auth_headers, fake_whatsapp,
):
    fake_whatsapp.reset()

    resp = await client.post(
        "/api/families/parents",
        headers=auth_headers,
        json={
            "family_id": str(seed_family["family_id"]),
            "name": "Geeta",
            "phone": "+919900777701",
            "whatsapp_id": "919900777701",
            "language": "hi",
            "role": "cook",
        },
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["role"] == "cook"

    # Card was sent
    sent = fake_whatsapp.messages_to("919900777701")
    assert len(sent) == 1
    btn_ids = [
        b["reply"]["id"]
        for b in sent[0].payload["interactive"]["action"]["buttons"]
    ]
    assert btn_ids[0].startswith("onboard_yes_")


@pytest.mark.asyncio
async def test_post_parents_with_role_parent_does_not_fire_card(
    client, db, seed_family, auth_headers, fake_whatsapp,
):
    fake_whatsapp.reset()

    resp = await client.post(
        "/api/families/parents",
        headers=auth_headers,
        json={
            "family_id": str(seed_family["family_id"]),
            "name": "Mom",
            "phone": "+919900777702",
            "whatsapp_id": "919900777702",
            "language": "hi",
            "role": "parent",
        },
    )
    assert resp.status_code == 200
    assert fake_whatsapp.messages_to("919900777702") == []


@pytest.mark.asyncio
async def test_post_register_cook_fires_card_on_fresh_insert(
    client, db, seed_family, fake_whatsapp,
):
    """The shared-cook registration endpoint creates a Parent + sends the card."""
    fake_whatsapp.reset()

    resp = await client.post(
        "/api/households/register-cook",
        json={
            "family_id": str(seed_family["family_id"]),
            "phone": "+919900777710",
            "name": "Sunita",
            "household_label": "Mehta House",
            "language": "hi",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_new"] is True

    sent = fake_whatsapp.messages_to("919900777710")
    assert len(sent) == 1
    assert sent[0].payload["type"] == "interactive"


@pytest.mark.asyncio
async def test_post_register_cook_does_not_re_fire_on_existing_parent(
    client, db, seed_family, fake_whatsapp,
):
    """Second register-cook call (same phone) must not re-greet."""
    body = {
        "family_id": str(seed_family["family_id"]),
        "phone": "+919900777711",
        "name": "Sunita",
        "household_label": "Mehta House",
        "language": "hi",
    }
    await client.post("/api/households/register-cook", json=body)
    fake_whatsapp.reset()

    # Second call should be a no-op for the welcome card
    resp = await client.post("/api/households/register-cook", json=body)
    assert resp.status_code == 200
    assert fake_whatsapp.messages_to("919900777711") == []


@pytest.mark.asyncio
async def test_resend_onboarding_endpoint_sends_card(
    client, db, seed_family, auth_headers, fake_whatsapp,
):
    cook = await _make_cook(db, seed_family["family_id"], phone="+919900777720")
    await db.commit()
    fake_whatsapp.reset()

    resp = await client.post(
        f"/api/households/cooks/{cook.id}/resend-onboarding",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"sent": True, "reason": None}
    assert len(fake_whatsapp.messages_to(cook.whatsapp_id)) == 1


@pytest.mark.asyncio
async def test_resend_onboarding_idempotent_when_already_onboarded(
    client, db, seed_family, auth_headers, fake_whatsapp,
):
    cook = await _make_cook(db, seed_family["family_id"], phone="+919900777721")
    cook.onboarded_at = datetime.now(UTC)
    await db.commit()
    fake_whatsapp.reset()

    resp = await client.post(
        f"/api/households/cooks/{cook.id}/resend-onboarding",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["sent"] is False
    assert body["reason"] == "already_onboarded"
    assert fake_whatsapp.messages_to(cook.whatsapp_id) == []


@pytest.mark.asyncio
async def test_resend_onboarding_reactivates_galat_number(
    client, db, seed_family, auth_headers, fake_whatsapp,
):
    """Cook said 'Galat number' but household corrected — resend must re-activate."""
    cook = await _make_cook(db, seed_family["family_id"], phone="+919900777722")
    cook.is_active = False
    await db.commit()
    fake_whatsapp.reset()

    resp = await client.post(
        f"/api/households/cooks/{cook.id}/resend-onboarding",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["sent"] is True

    await db.refresh(cook)
    assert cook.is_active is True


@pytest.mark.asyncio
async def test_resend_onboarding_404_for_unknown_parent(
    client, seed_family, auth_headers,
):
    ghost = uuid.uuid4()
    resp = await client.post(
        f"/api/households/cooks/{ghost}/resend-onboarding",
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_resend_onboarding_bypasses_feature_flag(
    client, db, seed_family, auth_headers, fake_whatsapp, monkeypatch,
):
    """Flag-off only blocks AUTO sends; ops resend is explicit and proceeds."""
    from app.config import settings
    monkeypatch.setattr(settings, "cook_onboarding_enabled", False)

    cook = await _make_cook(db, seed_family["family_id"], phone="+919900777723")
    await db.commit()
    fake_whatsapp.reset()

    resp = await client.post(
        f"/api/households/cooks/{cook.id}/resend-onboarding",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["sent"] is True
    assert len(fake_whatsapp.messages_to(cook.whatsapp_id)) == 1
