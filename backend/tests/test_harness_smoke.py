"""Smoke test for the test harness itself.

These tests exercise the conftest fixtures (engine, db rollback, ASGI
client, seed_family, auth_headers) without depending on any specific
business logic. If they pass, the harness is healthy.
"""

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


async def test_db_session_works(db):
    """The session fixture should connect to the test DB and return its name."""
    result = await db.execute(text("SELECT current_database()"))
    name = result.scalar_one()
    assert name == "bimi_pytest", f"Expected bimi_pytest, got {name}"


async def test_db_rollback_isolates_tests_part_1(db):
    """Insert a family inside this test."""
    import uuid

    from app.models.family import Family

    db.add(Family(
        id=uuid.UUID("00000000-0000-0000-0000-0000000000aa"),
        name="Isolation Test 1",
        family_type="household",
    ))
    await db.commit()

    # Verify the row exists in this transaction
    result = await db.execute(text("SELECT count(*) FROM families WHERE name = 'Isolation Test 1'"))
    assert result.scalar_one() == 1


async def test_db_rollback_isolates_tests_part_2(db):
    """The previous test's family should NOT be visible here — rollback worked."""
    result = await db.execute(text("SELECT count(*) FROM families WHERE name = 'Isolation Test 1'"))
    assert result.scalar_one() == 0, "Previous test's row leaked — DB isolation broken"


async def test_health_endpoint(client):
    """The /health endpoint should respond — proves ASGI in-process client works."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in ("ok", "degraded")


async def test_seed_family_creates_data(seed_family, db):
    """seed_family fixture should populate the test DB."""
    from app.models.family import Child, Family

    fam = await db.get(Family, seed_family["family_id"])
    assert fam is not None
    assert fam.name == "Test Family"

    child = await db.get(Child, seed_family["child_id"])
    assert child is not None
    assert child.phone == seed_family["phone"]


async def test_auth_headers_authenticate(client, auth_headers, seed_family):
    """The auth_headers fixture should produce a JWT that the bearer
    dependency accepts."""
    fid = seed_family["family_id"]
    resp = await client.get(f"/api/families/{fid}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "Test Family"


async def test_unauthenticated_request_is_rejected(client, seed_family):
    """Without auth_headers the same endpoint should 401."""
    fid = seed_family["family_id"]
    resp = await client.get(f"/api/families/{fid}")
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Adapter fixture smoke tests
# ---------------------------------------------------------------------------


async def test_fake_llm_returns_canned_intent(fake_llm):
    """The Fake LLM adapter should return canned intent JSON without httpx."""
    from app.adapters import get_llm_adapter

    adapter = get_llm_adapter()
    assert adapter is fake_llm, "fake_llm fixture should be the installed adapter"

    resp = await adapter.complete(
        prompt="dal banao", service="intent", response_format="json",
    )
    assert resp.json_payload is not None
    assert resp.json_payload["intent"] == "unknown"
    assert len(fake_llm.calls_for("intent")) == 1


async def test_fake_whatsapp_records_outbound(fake_whatsapp):
    """The Fake WhatsApp adapter should record every outbound message."""
    from app.adapters import get_whatsapp_adapter

    adapter = get_whatsapp_adapter()
    assert adapter is fake_whatsapp

    result = await adapter.send_message({
        "to": "+919900000099",
        "type": "text",
        "text": {"body": "Namaste!"},
    })
    assert result.message_id is not None
    sent = fake_whatsapp.messages_to("+919900000099")
    assert len(sent) == 1
    assert sent[0].text() == "Namaste!"


async def test_fake_transcription_with_test_marker(fake_transcription):
    """test:<text> audio bytes should round-trip as the literal text."""
    from app.adapters import get_transcription_adapter

    adapter = get_transcription_adapter()
    result = await adapter.transcribe(b"test:order milk and eggs", language="en")
    assert result.transcript == "order milk and eggs"
    assert result.confidence > 0.9
    assert result.source == "fake"


async def test_fake_swiggy_mcp_search(fake_mcp_swiggy):
    """The Fake Swiggy MCP adapter should return canned search results
    with brand-attribution metadata."""
    from app.adapters import Surface, get_mcp_swiggy_adapter

    adapter = get_mcp_swiggy_adapter()
    result = await adapter.search(Surface.INSTAMART, "atta")
    assert result.attribution == {"platform": "swiggy", "surface": "instamart"}
    assert len(result.items) == 2
    assert "atta" in result.items[0]["name"].lower()


async def test_fake_swiggy_mcp_idempotent_order(fake_mcp_swiggy):
    """Replaying a place_order with the same idempotency_key should return
    the same order_id."""
    from app.adapters import Surface, get_mcp_swiggy_adapter

    adapter = get_mcp_swiggy_adapter()
    items = [{"id": "x", "qty": 1}]
    a = await adapter.place_order(Surface.INSTAMART, items, idempotency_key="key-1")
    b = await adapter.place_order(Surface.INSTAMART, items, idempotency_key="key-1")
    c = await adapter.place_order(Surface.INSTAMART, items, idempotency_key="key-2")
    assert a.order_id == b.order_id, "idempotent replay should reuse the same order_id"
    assert a.order_id != c.order_id, "different keys should mint different orders"


async def test_fakes_are_isolated_between_tests_part_1(fake_llm):
    """Insert a call here; the next test should see an empty calls list."""
    await fake_llm.complete(prompt="ping", service="intent")
    assert len(fake_llm.calls) == 1


async def test_fakes_are_isolated_between_tests_part_2(fake_llm):
    """If the previous test leaked state, this assertion would fail."""
    assert len(fake_llm.calls) == 0


async def test_fake_otp_records_sends(fake_otp, db, client):
    """Tests can inject Fake OTP and inspect the sent code."""
    await fake_otp.send(phone="+919900000099", otp="123456")
    last = fake_otp.last_for("+919900000099")
    assert last == "123456"
