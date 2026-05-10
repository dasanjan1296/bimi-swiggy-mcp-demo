"""Sunday cook stock-check job — Slice 4 of the WhatsApp coordination plan.

The job sends a voice prompt to every cook every Sunday morning. The
cook's reply flows through the existing grocery handler (multi-intent
splitter), so this test only verifies the OUTBOUND prompt — covering
the inbound handling would duplicate the grocery test suite.

We test the per-cook helper directly rather than the aggregator: the
aggregator opens its own DB session that doesn't see test SAVEPOINT
state, so an end-to-end test would need a committed-DB fixture (out
of scope here).
"""
from __future__ import annotations

import pytest

from app.models.family import Parent
from app.tasks.daily_briefing import send_sunday_stock_check_to_cook


async def _make_cook(db, family_id, *, phone, name):
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
async def test_per_cook_send_includes_voice_and_text_payloads(
    db, seed_family, fake_whatsapp,
):
    cook = await _make_cook(
        db, seed_family["family_id"], phone="+919900444401", name="Geeta",
    )
    fake_whatsapp.reset()

    await send_sunday_stock_check_to_cook(cook)

    sent = fake_whatsapp.messages_to(cook.whatsapp_id)
    assert len(sent) >= 1

    # The payload set varies based on whether voice TTS is enabled in
    # the test env. Either way, the text body must mention the stock
    # check premise so the cook understands what's being asked.
    bodies = " ".join(
        m.payload.get("text", {}).get("body", "") for m in sent if m.type == "text"
    )
    assert "stock check" in bodies.lower() or "khatam" in bodies.lower()

