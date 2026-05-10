"""Voice-note coalescing — Slice 3 of the WhatsApp coordination plan.

Covers:
  - schedule_voice_dispatch buffers consecutive voice notes
  - Buffer holds concatenated transcripts + averaged confidence
  - Flush merges and dispatches through the normal text-routing path
  - Empty buffer flush is a safe no-op
  - Force-flush helper used by tests cancels the pending timer
"""
from __future__ import annotations

import asyncio

import pytest

from app.models.family import Parent
from app.services import voice_coalesce
from app.services.voice_coalesce import (
    _flush_now_for_tests,
    _peek_buffer_for_tests,
    _reset_buffers_for_tests,
    schedule_voice_dispatch,
)


@pytest.fixture(autouse=True)
def _clear_buffers():
    _reset_buffers_for_tests()
    yield
    _reset_buffers_for_tests()


async def _make_parent(db, family_id, *, phone="+919900333333", name="Geeta"):
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
    await db.commit()
    return p


@pytest.mark.asyncio
async def test_schedule_voice_dispatch_appends_to_buffer(db, seed_family):
    """Three consecutive voice notes within the window stack into one buffer."""
    parent = await _make_parent(db, seed_family["family_id"])

    await schedule_voice_dispatch(
        parent_id=parent.id, family_id=parent.family_id,
        sender_wa_id=parent.whatsapp_id, language="hi",
        transcript="doodh khatam", confidence=0.9,
    )
    await schedule_voice_dispatch(
        parent_id=parent.id, family_id=parent.family_id,
        sender_wa_id=parent.whatsapp_id, language="hi",
        transcript="aur paneer", confidence=0.85,
    )
    await schedule_voice_dispatch(
        parent_id=parent.id, family_id=parent.family_id,
        sender_wa_id=parent.whatsapp_id, language="hi",
        transcript="aur ek dozen anda", confidence=0.95,
    )

    buf = _peek_buffer_for_tests(parent.whatsapp_id)
    assert buf is not None
    assert len(buf.transcripts) == 3
    transcripts = [t for t, _ in buf.transcripts]
    assert transcripts == ["doodh khatam", "aur paneer", "aur ek dozen anda"]


@pytest.mark.asyncio
async def test_schedule_voice_dispatch_resets_timer_on_each_arrival(db, seed_family):
    """Each new voice note cancels the prior timer (to extend the window)."""
    parent = await _make_parent(db, seed_family["family_id"])

    await schedule_voice_dispatch(
        parent_id=parent.id, family_id=parent.family_id,
        sender_wa_id=parent.whatsapp_id, language="hi",
        transcript="first", confidence=0.9,
    )
    first_timer = _peek_buffer_for_tests(parent.whatsapp_id).timer

    await schedule_voice_dispatch(
        parent_id=parent.id, family_id=parent.family_id,
        sender_wa_id=parent.whatsapp_id, language="hi",
        transcript="second", confidence=0.9,
    )
    second_timer = _peek_buffer_for_tests(parent.whatsapp_id).timer

    assert first_timer is not second_timer
    # Cancellation is mid-flight when schedule returns; yield once so
    # the event loop processes the CancelledError and marks the task.
    await asyncio.sleep(0)
    assert first_timer.cancelled() or first_timer.done()


@pytest.mark.asyncio
async def test_flush_concatenates_and_clears_buffer(
    db, seed_family, monkeypatch,
):
    """Flush concatenates transcripts and hands off to the dispatcher once."""
    parent = await _make_parent(db, seed_family["family_id"])

    received: list[dict] = []

    async def fake_dispatch(**kwargs):
        received.append(kwargs)

    monkeypatch.setattr(voice_coalesce, "_dispatch_combined_transcript", fake_dispatch)

    await schedule_voice_dispatch(
        parent_id=parent.id, family_id=parent.family_id,
        sender_wa_id=parent.whatsapp_id, language="hi",
        transcript="doodh khatam", confidence=0.9,
    )
    await schedule_voice_dispatch(
        parent_id=parent.id, family_id=parent.family_id,
        sender_wa_id=parent.whatsapp_id, language="hi",
        transcript="aur paneer chahiye", confidence=0.8,
    )

    await _flush_now_for_tests(parent.whatsapp_id)

    assert len(received) == 1
    call = received[0]
    assert call["text"] == "doodh khatam aur paneer chahiye"
    assert call["confidence"] == pytest.approx(0.85, abs=0.001)
    assert call["sender_wa_id"] == parent.whatsapp_id
    # Buffer is cleared post-flush.
    assert _peek_buffer_for_tests(parent.whatsapp_id) is None


@pytest.mark.asyncio
async def test_flush_empty_buffer_is_noop(monkeypatch):
    received: list = []

    async def fake_dispatch(**kwargs):
        received.append(kwargs)

    monkeypatch.setattr(voice_coalesce, "_dispatch_combined_transcript", fake_dispatch)

    await _flush_now_for_tests("nonexistent_wa_id")
    assert received == []


@pytest.mark.asyncio
async def test_flush_swallows_dispatch_failures(monkeypatch):
    """A crash inside the dispatcher must not propagate up to the timer."""
    async def boom(**kwargs):
        raise RuntimeError("downstream broke")

    monkeypatch.setattr(voice_coalesce, "_dispatch_combined_transcript", boom)

    import uuid as uuid_mod
    await schedule_voice_dispatch(
        parent_id=uuid_mod.uuid4(),
        family_id=uuid_mod.uuid4(),
        sender_wa_id="someone",
        language="hi",
        transcript="anything",
        confidence=0.5,
    )
    # Should not raise.
    await _flush_now_for_tests("someone")
    assert _peek_buffer_for_tests("someone") is None


@pytest.mark.asyncio
async def test_window_constant_is_ten_seconds():
    """Sanity: the spec says 10s; regressions should fail loudly."""
    assert voice_coalesce.COALESCE_WINDOW_SEC == 10.0
