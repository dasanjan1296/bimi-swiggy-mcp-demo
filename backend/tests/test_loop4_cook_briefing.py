"""Loop 4: cook briefing flow — WhatsApp webhook + voice + text dispatch.

The Instacook pool-cook job-handling subsystem was removed in Phase 0.3, so
the cook-briefing flow is now PURELY about the household's regular cook
(Malti Didi / Geeta Didi) reaching Bimi via WhatsApp:

  - Webhook signature verification (covered in Loop 1)
  - GET handshake (verify token)
  - POST: malformed payloads, status updates, unknown senders, replays
  - SharedCook routing for cooks who serve multiple households
  - Background-task dispatch (the actual intent extraction is async)

We do NOT test the inline AI calls (intent extraction, transcription,
meal queries) here — those go through the FakeLLM/FakeTranscription
adapters. Their behavior is covered in tests/test_harness_smoke.py.
"""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# GET handshake
# ---------------------------------------------------------------------------


class TestWebhookHandshake:
    async def test_correct_token_echoes_challenge_as_plain_text(self, client):
        r = await client.get(
            "/api/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "bimi-verify",
                "hub.challenge": "12345",
            },
        )
        assert r.status_code == 200, r.text
        # Meta verifies by looking for the exact challenge in the body
        assert r.text == "12345"
        # Plain-text content type — Meta rejects JSON for the handshake
        assert "text/plain" in r.headers.get("content-type", "")

    async def test_wrong_verify_token_returns_403(self, client):
        r = await client.get(
            "/api/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "WRONG",
                "hub.challenge": "12345",
            },
        )
        assert r.status_code == 403, (
            f"Wrong verify token must 403, not 200 with body. Got {r.status_code}."
        )

    async def test_missing_mode_returns_403(self, client):
        r = await client.get(
            "/api/webhook",
            params={"hub.verify_token": "bimi-verify", "hub.challenge": "12345"},
        )
        assert r.status_code == 403

    async def test_missing_challenge_returns_empty_200(self, client):
        """Meta sometimes pings the GET endpoint without a challenge for
        health-check purposes. Don't 500 — return an empty 200 so the
        webhook stays marked healthy."""
        r = await client.get(
            "/api/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "bimi-verify",
            },
        )
        assert r.status_code == 200
        assert r.text == ""


# ---------------------------------------------------------------------------
# POST robustness
# ---------------------------------------------------------------------------


class TestWebhookPostRobustness:
    async def test_invalid_json_body_returns_200_and_logs(self, client):
        """Meta sometimes proxies through a CDN that strips the body.
        We must still ack so Meta doesn't retry-storm us."""
        r = await client.post(
            "/api/webhook",
            content=b"not json at all",
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["ignored"] == "invalid_json"

    async def test_top_level_array_body_returns_200(self, client):
        """Top-level JSON array (rare but possible from a misconfigured
        webhook proxy) — accept gracefully, don't crash."""
        r = await client.post("/api/webhook", json=[1, 2, 3])
        assert r.status_code == 200
        assert r.json()["ignored"] == "non_object_body"

    async def test_payload_with_unknown_top_level_keys_does_not_500(self, client):
        """Future Meta schema additions should not crash us."""
        r = await client.post(
            "/api/webhook",
            json={"object": "whatsapp_business_account", "future_key": {"x": 1}},
        )
        assert r.status_code < 500

    async def test_payload_with_only_status_updates_skips_cleanly(self, client):
        """Status delivery / read receipts arrive with `statuses`, not
        `messages`. Must be a no-op success."""
        r = await client.post(
            "/api/webhook",
            json={
                "entry": [{
                    "changes": [{
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": "x"},
                            "statuses": [
                                {"id": "wamid.x", "status": "sent",
                                 "recipient_id": "+919900000099"},
                            ],
                        },
                    }],
                }],
            },
        )
        assert r.status_code == 200
        assert r.json()["status"] in ("received", "no entries")

    async def test_payload_with_message_but_missing_from_field_skipped(self, client):
        """A message with no `from` field can't be routed. We log + skip,
        not 500."""
        r = await client.post(
            "/api/webhook",
            json={
                "entry": [{
                    "changes": [{
                        "value": {
                            "messages": [{
                                "type": "text",
                                "text": {"body": "anonymous"},
                                "id": f"wamid.{uuid.uuid4().hex}",
                            }],
                        },
                    }],
                }],
            },
        )
        assert r.status_code < 500

    async def test_text_message_from_known_parent_returns_200(
        self, client, db, seed_family,
    ):
        """End-to-end happy path: known parent sends a text message,
        webhook accepts and queues for background processing."""
        from app.models.family import Parent

        # Add a parent on the seed family
        parent = Parent(
            family_id=seed_family["family_id"],
            name="Webhook Test Parent",
            phone="+919800000200",
            whatsapp_id="919800000200",
            language="hi",
            role="parent",
        )
        db.add(parent)
        await db.commit()

        r = await client.post(
            "/api/webhook",
            json={
                "entry": [{
                    "changes": [{
                        "value": {
                            "messages": [{
                                "from": "919800000200",
                                "type": "text",
                                "text": {"body": "milk khareed lo"},
                                "id": f"wamid.{uuid.uuid4().hex}",
                            }],
                        },
                    }],
                }],
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "received"


# ---------------------------------------------------------------------------
# Cook context — household resolution
# ---------------------------------------------------------------------------


class TestCookContextResolution:
    """The SharedCook lookup + household resolution logic was the most
    bug-prone area in Loop 4 (4 lazy-load bugs found and fixed). These
    tests pin the fix end-to-end."""

    async def test_lookup_shared_cook_returns_none_for_unknown_phone(self, db):
        from app.services.cook_context import lookup_shared_cook

        result = await lookup_shared_cook("919999999999", db)
        assert result is None

    async def test_resolve_household_for_single_household_cook(
        self, client, seed_family, db,
    ):
        """A cook linked to ONE household should resolve cleanly to that
        household without disambiguation."""
        from app.services.cook_context import lookup_shared_cook, resolve_household

        # Register the cook via the API (covers the Loop 1 lazy-load fix path)
        await client.post(
            "/api/households/register-cook",
            json={
                "family_id": str(seed_family["family_id"]),
                "phone": "+919800000301",
                "name": "Solo Cook",
                "household_label": "Test House",
            },
        )

        cook = await lookup_shared_cook("919800000301", db)
        assert cook is not None

        result = await resolve_household(cook, "anything", db)
        assert result.family_id == seed_family["family_id"]
        assert result.resolution_method == "single_household"

    async def test_resolve_household_returns_no_households_for_unlinked_cook(
        self, db,
    ):
        """Edge case: a SharedCook with zero active households."""
        from app.models.shared_cook import SharedCook
        from app.services.cook_context import resolve_household

        cook = SharedCook(
            phone="919800000302",
            whatsapp_id="919800000302",
            name="Lonely Cook",
            language="hi",
        )
        db.add(cook)
        await db.commit()

        result = await resolve_household(cook, None, db)
        assert result.family_id is None
        assert result.resolution_method == "no_households"

    async def test_get_active_households_explicit_query(
        self, client, seed_family, db,
    ):
        """Pin the Loop 4 fix: `get_active_households` now requires `db`
        and uses an explicit query (no lazy load)."""
        from app.services.cook_context import (
            get_active_households,
            lookup_shared_cook,
        )

        await client.post(
            "/api/households/register-cook",
            json={
                "family_id": str(seed_family["family_id"]),
                "phone": "+919800000303",
                "name": "Test Cook",
                "household_label": "Test House",
            },
        )

        cook = await lookup_shared_cook("919800000303", db)
        assert cook is not None

        active = await get_active_households(cook, db)
        assert len(active) == 1
        assert active[0].family_id == seed_family["family_id"]


# ---------------------------------------------------------------------------
# WhatsApp adapter wiring (FakeWhatsAppAdapter records outbound)
# ---------------------------------------------------------------------------


class TestWhatsAppAdapter:
    async def test_send_text_message_routes_through_fake(
        self, fake_whatsapp,
    ):
        """The shared `services/whatsapp.send_text_message` helper used to
        speak directly to httpx. Loop 5 will migrate it to use the
        `WhatsAppAdapter` Protocol — until then, it talks directly to the
        Cloud API. This test pins the CURRENT contract: at minimum, the
        adapter's `set_whatsapp_adapter` swap doesn't break anything when
        the real send happens via httpx (which fails without WHATSAPP_TOKEN
        but doesn't raise)."""
        from app.adapters import get_whatsapp_adapter

        adapter = get_whatsapp_adapter()
        result = await adapter.send_message({
            "to": "+919900000001",
            "type": "text",
            "text": {"body": "Aaj dal-rice banao"},
        })
        assert result.message_id is not None
        recorded = fake_whatsapp.last()
        assert recorded is not None
        assert recorded.text() == "Aaj dal-rice banao"

    async def test_download_media_returns_canned_audio(
        self, fake_whatsapp,
    ):
        from app.adapters import get_whatsapp_adapter

        adapter = get_whatsapp_adapter()
        fake_whatsapp.set_media("media-id-test", b"\x00\x01\x02fake audio")

        content = await adapter.download_media("media-id-test")
        assert content == b"\x00\x01\x02fake audio"

    async def test_download_media_returns_empty_for_unknown(
        self, fake_whatsapp,
    ):
        from app.adapters import get_whatsapp_adapter

        adapter = get_whatsapp_adapter()
        content = await adapter.download_media("never-set")
        assert content == b""


# ---------------------------------------------------------------------------
# Transcription adapter wiring
# ---------------------------------------------------------------------------


class TestTranscriptionAdapter:
    async def test_test_marker_round_trips(self, fake_transcription):
        from app.adapters import get_transcription_adapter

        adapter = get_transcription_adapter()
        result = await adapter.transcribe(
            b"test:tomato 1kg laana", language="hi",
        )
        assert result.transcript == "tomato 1kg laana"
        assert result.confidence > 0.9

    async def test_canned_audio_by_fingerprint(self, fake_transcription):
        from app.adapters import TranscriptionResult, get_transcription_adapter

        adapter = get_transcription_adapter()
        audio = b"\x00\x01\x02\x03some opaque bytes"
        fake_transcription.set_canned_for_audio(
            audio,
            TranscriptionResult(
                transcript="aaj nahi aaungi",
                confidence=0.92,
                language="hi",
                source="fake",
            ),
        )

        result = await adapter.transcribe(audio, language="hi")
        assert result.transcript == "aaj nahi aaungi"
        assert result.confidence == 0.92

    async def test_unknown_audio_returns_empty_failed(self, fake_transcription):
        from app.adapters import get_transcription_adapter

        adapter = get_transcription_adapter()
        result = await adapter.transcribe(b"\xff" * 100, language="hi")
        assert result.transcript == ""
        assert result.source == "failed"


# ---------------------------------------------------------------------------
# Webhook signature replay protection
# ---------------------------------------------------------------------------


class TestWebhookReplayProtection:
    """Meta sometimes redelivers the same `message.id` (network retry,
    proxy hiccup). We dedupe via background task — the same message.id
    should be processed at most once.

    This is currently NOT enforced (no dedup table exists). Pinned as
    `xfail` for Loop 9 — when we add a `whatsapp_message_dedup` table
    + a unique-constraint check, this test starts passing."""

    async def test_same_message_id_dispatched_at_most_once(
        self, client, db, seed_family,
    ):
        """Loop 9: webhook deduplication via `whatsapp_message_dedup` (mig 045).
        Same message_id delivered N times → dispatched ONCE, deduped (N-1) times.
        Verified at the receive_webhook layer (counts in the response body)
        rather than the post-dispatch DB state, because BackgroundTasks run
        outside the test request lifecycle."""
        msg_id = f"wamid.{uuid.uuid4().hex}"
        payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "from": "919800000401",
                            "type": "text",
                            "text": {"body": "milk laana"},
                            "id": msg_id,
                        }],
                    },
                }],
            }],
        }

        first = (await client.post("/api/webhook", json=payload)).json()
        second = (await client.post("/api/webhook", json=payload)).json()
        third = (await client.post("/api/webhook", json=payload)).json()

        assert first.get("dispatched") == 1, first
        assert first.get("deduped") == 0, first

        assert second.get("dispatched") == 0
        assert second.get("deduped") == 1

        assert third.get("dispatched") == 0
        assert third.get("deduped") == 1
