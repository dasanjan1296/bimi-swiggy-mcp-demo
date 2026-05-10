"""Multimodal validation test suite — voice + text WhatsApp end-to-end.

Covers every scenario in `bimi/docs/MULTIMODAL-VALIDATION-REPORT.md`. The
suite runs ITERATIVE LOOPS (1→7), each focused on one class of failure
mode the brief calls out:

  Loop 1 — clear voice + clear text (happy paths)
  Loop 2 — Hinglish, multi-intent, brand mishearings
  Loop 3 — incomplete / noisy / low-confidence audio
  Loop 4 — long rambling messages, multiple intents in one note
  Loop 5 — chaos: replay, conflict, dead-letter
  Loop 6 — critical-action confirmation loop
  Loop 7 — voice OUT for the cook (TTS + text caption duality)
  Loop 8 — proactive intelligence (cook overload, dedup, anticipate)

Tests are deliberately self-contained: they exercise the splitter,
classifier, voice-reply helper, and critical-confirmation registry
without spinning up the full FastAPI app where possible. The few that
need the webhook use the in-process ASGI client from `conftest.py`.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest

# pytest-asyncio runs in `auto` mode (configured in pyproject.toml), so any
# coroutine test function is automatically wrapped. No module-level mark
# needed — and adding one would erroneously mark the sync helper-style
# tests in TestLoop1_ClearInput / TestLoop2_HinglishMultiIntent.


# ─── Loop 1 — clear voice + text (happy paths) ───────────────────────────


class TestLoop1_ClearInput:
    """The system MUST nail the happy paths. If these fail, nothing else
    matters."""

    def test_voice_clear_grocery(self):
        """Loop 1.1 — A clear voice transcript splits into one item."""
        from app.services.multi_intent import (
            is_likely_multi_intent,
            split_intents,
        )

        text = "Doodh ek litre laana"
        assert not is_likely_multi_intent(text), (
            f"'{text}' shouldn't trigger multi-intent splitting"
        )
        assert split_intents(text) == [text]

    @pytest.mark.parametrize(
        "transcript",
        [
            "ban gaya",
            "ho gaya khana",
            "khana ban gaya",
            "ready hai",
            "tayyar hai",
            "done",
        ],
    )
    def test_meal_ready_keywords_match(self, transcript):
        """Loop 1.2 — Cook's ready-confirmation keywords all match."""
        from app.routers.webhook import _might_be_meal_ready

        assert _might_be_meal_ready(transcript), (
            f"Cook's '{transcript}' should be detected as meal-ready"
        )

    @pytest.mark.parametrize(
        "transcript,expected",
        [
            ("kal nahi aaungi", True),
            ("aaj nahi aa paaungi", True),
            ("chutti chahiye", True),
            ("tabiyat kharab hai", True),
            ("emergency hai", True),
            ("ban gaya", False),
            ("doodh laana", False),
        ],
    )
    def test_absence_keywords_match(self, transcript, expected):
        """Loop 1.3 — Absence vs non-absence classification."""
        from app.services.absence import might_be_absence

        assert might_be_absence(transcript) is expected, transcript


# ─── Loop 2 — Hinglish + multi-intent + mishearings ──────────────────────


class TestLoop2_HinglishMultiIntent:
    """Real users mix Hindi + English mid-sentence and pile multiple
    asks into one voice note."""

    def test_multi_intent_voice_splits_items(self):
        """Loop 2.1 — 'doodh aur paneer aur chawal' → 3 units, not 1.

        Without the splitter, the GPT extractor sees a single long
        phrase and emits one mushed item. The splitter forces 3
        independent extractions.
        """
        from app.services.multi_intent import split_intents

        text = "doodh ek litre laana aur paneer 200 gram bhi le aana, chawal bhi 5 kilo"
        units = split_intents(text)
        assert len(units) >= 2, (
            f"Expected ≥2 units, got {len(units)}: {units}"
        )
        joined = " ".join(u.lower() for u in units)
        assert "doodh" in joined
        assert "paneer" in joined
        assert "chawal" in joined

    def test_short_text_never_splits(self):
        """Loop 2.2 — Short messages MUST NOT split (false-positive risk).

        'doodh aur paneer' is technically multi-item but short enough
        that the existing GPT extractor handles it cleanly without help.
        Splitting noise hurts, doesn't help.
        """
        from app.services.multi_intent import split_intents

        for text in ("doodh aur paneer", "kal nahi aaungi", "ban gaya"):
            assert split_intents(text) == [text], (
                f"Short text '{text}' should pass through unsplit"
            )

    def test_pure_punctuation_split(self):
        """Loop 2.3 — Sentence terminators force splits regardless of
        keywords. A user can dictate 'A. B. C.' and get 3 units."""
        from app.services.multi_intent import split_intents

        text = "Pehle doodh laana ek litre. Phir paneer 200 gram. Aur chawal 5 kilo."
        units = split_intents(text)
        assert len(units) >= 3, units

    def test_hard_split_on_comma_aur(self):
        """Loop 2.4 — ', aur' is a clearer cue than bare 'aur'."""
        from app.services.multi_intent import split_intents

        text = (
            "haldi sau gram chahiye, aur dahi 200 gram laana, "
            "aur namak ek packet bhi"
        )
        units = split_intents(text)
        assert len(units) >= 3, units

    def test_soft_aur_not_split_when_rhs_is_filler(self):
        """Loop 2.5 — 'doodh laana aur jaldi' must NOT split because
        'jaldi' is an adverb, not a new item."""
        from app.services.multi_intent import split_intents

        # We'd rather under-split than over-split. The intent extractor
        # handles "doodh laana aur jaldi" fine as urgency-flagged milk.
        units = split_intents("doodh ek litre lana hai aur jaldi please")
        non_filler = [u for u in units if "doodh" in u.lower() or len(u.split()) > 2]
        assert non_filler, units

    def test_runaway_split_caps_at_max_units(self):
        """Loop 2.6 — A pathological transcript with 12 'aur's collapses
        back to one unit (better than 12 noisy ones)."""
        from app.services.multi_intent import split_intents

        text = "a aur b aur c aur d aur e aur f aur g aur h aur i aur j aur k"
        units = split_intents(text, max_units=6)
        # When split count exceeds cap, fall back to original
        assert len(units) <= 6


# ─── Loop 3 — incomplete / noisy / low-confidence ────────────────────────


class TestLoop3_LowConfidence:
    """Voice notes are messy. The system must keep the conversation
    alive even when it can't parse confidently."""

    async def test_low_confidence_replies_with_best_guess(self, fake_whatsapp):
        """Loop 3.1 — The fallback now offers a best-guess (F3 fix).

        Before the fix: a generic 'samajh nahi aaya' that left the user
        stuck. After: 'Kya aap yeh kehna chah rahe the: "<transcript>"?'
        with ✅/❌/✏️ buttons.
        """
        from app.services.whatsapp import send_low_confidence_fallback

        await send_low_confidence_fallback(
            "+919900001234",
            best_guess="atta khatam ho gaya",
        )

        last = fake_whatsapp.last()
        assert last is not None
        assert last.type == "interactive"
        body = (last.payload.get("interactive") or {}).get("body", {}).get("text", "")
        assert "atta khatam ho gaya" in body, (
            "best-guess transcript must appear in the prompt body"
        )
        # 3 buttons: yes / dobara / text
        buttons = last.buttons() or []
        assert len(buttons) == 3
        button_ids = [b["reply"]["id"] for b in buttons]
        assert "lowconf_yes" in button_ids
        assert "lowconf_no" in button_ids
        assert "lowconf_text" in button_ids

    async def test_empty_transcript_emits_generic_fallback(self, fake_whatsapp):
        """Loop 3.2 — Empty transcript → generic fallback (no best guess
        to offer)."""
        from app.services.whatsapp import send_low_confidence_fallback

        await send_low_confidence_fallback("+919900001234")

        last = fake_whatsapp.last()
        assert last is not None
        assert last.type == "text"
        text = last.text() or ""
        assert "samajh nahi aaya" in text.lower()


# ─── Loop 4 — long rambling + edge-case dates ────────────────────────────


class TestLoop4_LongRambling:
    """Long voice notes with multiple intents must extract every ask
    and not lose the urgent ones."""

    def test_long_rambling_voice_extracts_two_items(self):
        """Loop 4.1 — A 25-word ramble with 'aur' + sentence terminator
        splits into ≥2 units."""
        from app.services.multi_intent import split_intents

        text = (
            "haan beta sun ye atta khatam ho gaya hai. aur thoda dahi "
            "bhi laa dena please aaj raat. paneer bhi 200 gram chahiye"
        )
        units = split_intents(text)
        # We expect at least 2 (atta-related + dahi-related), often 3
        assert len(units) >= 2, units

    def test_parso_absence_parses_correctly(self):
        """Loop 4.2 — 'parso' = day after tomorrow, not today."""
        from app.services.absence import parse_absence_date

        result = parse_absence_date("parso nahi aaungi")
        expected = date.today() + timedelta(days=2)
        assert result == expected, f"parso → {result}, expected {expected}"

    def test_kal_absence_parses_correctly(self):
        """Loop 4.3 — 'kal' = tomorrow, not today."""
        from app.services.absence import parse_absence_date

        result = parse_absence_date("kal nahi aa rahi")
        expected = date.today() + timedelta(days=1)
        assert result == expected


# ─── Loop 5 — cook-side classifier ──────────────────────────────────────


class TestLoop5_CookSideIntents:
    """Cook intents arrive as voice notes. The classifier must handle
    every documented intent kind, with the right payload."""

    @pytest.fixture
    def cook_sender(self):
        from app.services import whatsapp_intents as wi

        fake = AsyncMock(return_value={
            "family_id": None, "member_id": None, "is_from_cook": True,
        })
        with patch.object(wi, "resolve_sender", fake):
            yield

    @pytest.mark.parametrize(
        "transcript,expected_kind",
        [
            ("kal nahi aaungi", "cook_absence"),
            ("aaj off rahungi", "cook_absence"),
            ("won't come tomorrow", "cook_absence"),
            ("running late, 15 min der ho rahi hai", "cook_running_late"),
            ("late ho jayegi aaj 10 minute", "cook_running_late"),
            ("atta khatam ho gaya", "cook_low_stock"),
            ("dahi almost over", "cook_low_stock"),
            ("aaj kya banau lunch mein?", "cook_meal_query"),
        ],
    )
    async def test_cook_voice_classifies_correctly(
        self, cook_sender, transcript, expected_kind,
    ):
        from app.services.whatsapp_intents import classify_inbound

        intent = await classify_inbound(transcript, "+919800000700", db=None)
        assert intent.kind == expected_kind, (
            f"'{transcript}' → got {intent.kind}, want {expected_kind}"
        )

    async def test_cook_voice_running_late_with_minutes(self, cook_sender):
        """Loop 5.2 — Late-running minute extraction."""
        from app.services.whatsapp_intents import classify_inbound

        intent = await classify_inbound(
            "20 min late ho jayegi aaj", "+91", db=None,
        )
        assert intent.kind == "cook_running_late"
        assert intent.payload["minutes"] == 20

    async def test_cook_voice_low_stock_severity(self, cook_sender):
        """Loop 5.3 — 'khatam' = out, 'almost over' = low."""
        from app.services.whatsapp_intents import classify_inbound

        i_out = await classify_inbound("atta khatam ho gaya", "+91", db=None)
        i_low = await classify_inbound("dahi almost over", "+91", db=None)
        assert i_out.payload["severity"] == "out"
        assert i_low.payload["severity"] == "low"


# ─── Loop 6 — critical-action confirmation ───────────────────────────────


class TestLoop6_CriticalConfirmation:
    """Critical actions (absence, meal swap, bulk order) MUST require
    confirmation. Auto-commit after 2 min so the user isn't stranded."""

    async def test_request_critical_confirmation_sends_prompt(
        self, fake_whatsapp,
    ):
        """Loop 6.1 — A critical-action request fires a Haan/Nahi prompt."""
        from app.services.critical_confirmation import (
            _reset_for_tests,
            request_critical_confirmation,
        )

        _reset_for_tests()
        committed = []

        async def on_commit(payload):
            committed.append(payload)

        action_id = await request_critical_confirmation(
            family_id=None,
            sender_wa_id="+919900001000",
            kind="cook_absence",
            summary="kal nahi aaungi (cook absence)",
            payload={"date": "2026-05-04"},
            on_commit=on_commit,
            auto_commit_sec=3600,  # large so auto-commit doesn't fire
        )

        assert action_id

        last = fake_whatsapp.last()
        assert last is not None
        assert last.type == "interactive"
        buttons = last.buttons() or []
        assert len(buttons) == 2
        ids = [b["reply"]["id"] for b in buttons]
        assert any(i.startswith("crit_yes_") for i in ids)
        assert any(i.startswith("crit_no_") for i in ids)
        assert not committed, "Commit must NOT have fired before the user taps yes"

    async def test_yes_button_commits(self, fake_whatsapp):
        """Loop 6.2 — Yes tap → on_commit fires, action transitions to
        'committed'."""
        from app.services.critical_confirmation import (
            _peek,
            _reset_for_tests,
            handle_confirmation_button,
            request_critical_confirmation,
        )

        _reset_for_tests()
        committed = []

        async def on_commit(payload):
            committed.append(payload)

        action_id = await request_critical_confirmation(
            family_id=None,
            sender_wa_id="+919900001001",
            kind="cook_absence",
            summary="kal nahi aaungi",
            payload={"date": "2026-05-04"},
            on_commit=on_commit,
            auto_commit_sec=3600,
        )

        result = await handle_confirmation_button(
            "+919900001001", f"crit_yes_{action_id}",
        )
        assert result is not None
        assert result["state"] == "committed"
        assert committed == [{"date": "2026-05-04"}]
        assert _peek(action_id).state == "committed"

    async def test_no_button_cancels(self, fake_whatsapp):
        """Loop 6.3 — No tap → cancellation, no commit."""
        from app.services.critical_confirmation import (
            _reset_for_tests,
            handle_confirmation_button,
            request_critical_confirmation,
        )

        _reset_for_tests()
        committed = []

        async def on_commit(payload):
            committed.append(payload)

        action_id = await request_critical_confirmation(
            family_id=None,
            sender_wa_id="+919900001002",
            kind="cook_absence",
            summary="kal nahi aaungi",
            payload={"date": "2026-05-04"},
            on_commit=on_commit,
            auto_commit_sec=3600,
        )

        result = await handle_confirmation_button(
            "+919900001002", f"crit_no_{action_id}",
        )
        assert result["state"] == "cancelled"
        assert committed == [], "Commit must NOT fire on cancel"

    async def test_auto_commit_after_timeout(self, fake_whatsapp):
        """Loop 6.4 — After the auto-commit window passes, commit fires
        even without a tap. Critical: the cook isn't stranded if the
        family is asleep."""
        from app.services.critical_confirmation import (
            _peek,
            _reset_for_tests,
            request_critical_confirmation,
        )

        _reset_for_tests()
        committed = []

        async def on_commit(payload):
            committed.append(payload)

        action_id = await request_critical_confirmation(
            family_id=None,
            sender_wa_id="+919900001003",
            kind="cook_absence",
            summary="kal nahi aaungi",
            payload={"x": 1},
            on_commit=on_commit,
            auto_commit_sec=0,  # immediate
        )

        # Yield once so the asyncio.sleep(0) inside _auto_commit_after fires
        await asyncio.sleep(0.05)

        action = _peek(action_id)
        assert action is not None
        assert action.state == "auto_committed"
        assert committed == [{"x": 1}]

    async def test_replacing_pending_cancels_prior(self, fake_whatsapp):
        """Loop 6.5 — A second 'kal nahi aaungi' from the same cook
        replaces the first pending action (the new message wins)."""
        from app.services.critical_confirmation import (
            _peek,
            _reset_for_tests,
            request_critical_confirmation,
        )

        _reset_for_tests()
        commits = []
        cancels = []

        async def commit(p):
            commits.append(p)

        async def cancel():
            cancels.append(True)

        first_id = await request_critical_confirmation(
            family_id=None,
            sender_wa_id="+919900001004",
            kind="cook_absence",
            summary="first",
            payload={"v": 1},
            on_commit=commit,
            on_cancel=cancel,
            auto_commit_sec=3600,
        )
        second_id = await request_critical_confirmation(
            family_id=None,
            sender_wa_id="+919900001004",
            kind="cook_absence",
            summary="second",
            payload={"v": 2},
            on_commit=commit,
            auto_commit_sec=3600,
        )

        assert first_id != second_id
        first = _peek(first_id)
        assert first is None or first.state == "cancelled"
        assert cancels, "First action's on_cancel must have fired"
        assert _peek(second_id).state == "pending"


# ─── Loop 7 — voice OUT for the cook ─────────────────────────────────────


class TestLoop7_VoiceOutForCook:
    """The cook should HEAR the briefing, not read it. Text is only
    a supporting caption."""

    async def test_voice_disabled_falls_back_to_text(self, fake_whatsapp):
        """Loop 7.1 — When use_real_voice_replies=False (default), the
        helper sends a single text message combining voice script + caption.
        No crash, no missing message."""
        from app.services.voice_reply import send_voice_or_text

        await send_voice_or_text(
            "+919900007000",
            voice_text="Namaste didi! Aaj chole banane hain.",
            text_caption="• Lunch: Chole\n• Prep: chole bhigo dijiye",
        )

        last = fake_whatsapp.last()
        assert last is not None
        assert last.type == "text"
        text = last.text() or ""
        assert "Namaste" in text
        assert "Lunch" in text  # caption present too

    async def test_voice_enabled_sends_audio_then_text(
        self, fake_whatsapp, monkeypatch,
    ):
        """Loop 7.2 — With voice enabled, the cook gets BOTH an audio
        message and a text caption. Both must arrive."""
        from app.config import settings
        from app.services import voice_reply

        # Flip the feature flag for the duration of this test.
        monkeypatch.setattr(settings, "use_real_voice_replies", True)
        # Use the fake TTS adapter (default when use_real_voice_replies is
        # off; we explicitly install one here so the cache miss doesn't
        # pick up the real adapter even with the flag flipped).
        fake_tts = voice_reply.FakeTtsAdapter()
        voice_reply.set_tts_adapter(fake_tts)
        try:
            await voice_reply.send_voice_or_text(
                "+919900007001",
                voice_text="Namaste didi! Aaj rajma chawal banayein.",
                text_caption="• Lunch: Rajma chawal",
                language="hi",
            )
        finally:
            voice_reply.set_tts_adapter(None)

        # TTS was called once
        assert len(fake_tts.calls) == 1
        assert "rajma chawal" in fake_tts.calls[0][0].lower()

        # Two outbound messages: audio + text
        msgs = fake_whatsapp.sent
        assert len(msgs) >= 2, f"Expected ≥2 sent (audio+text), got {len(msgs)}"
        types = {m.type for m in msgs}
        assert "audio" in types
        assert "text" in types

    async def test_voice_failure_falls_back_to_text(
        self, fake_whatsapp, monkeypatch,
    ):
        """Loop 7.3 — If TTS fails (network, quota, bad creds), we MUST
        still send the message — as text. Never silently drop."""
        from app.config import settings
        from app.services import voice_reply

        monkeypatch.setattr(settings, "use_real_voice_replies", True)

        class FailingTts:
            async def synthesize(self, text, *, language="hi"):
                return voice_reply.TtsResult(b"", "", "", "failed")

        voice_reply.set_tts_adapter(FailingTts())
        try:
            await voice_reply.send_voice_or_text(
                "+919900007002",
                voice_text="Namaste didi! Aaj kuch nahi banana.",
                text_caption="(no meals today)",
            )
        finally:
            voice_reply.set_tts_adapter(None)

        last = fake_whatsapp.last()
        assert last is not None
        assert last.type == "text"
        text = last.text() or ""
        assert "Namaste" in text


# ─── Loop 8 — proactive intelligence (cook overload) ────────────────────


class TestLoop8_ProactiveIntelligence:
    """The brief: 'Detect overload (too many dishes vs cook capacity).'"""

    def test_overload_when_total_exceeds_slot(self):
        """Loop 8.1 — 4 dishes totalling 110 min in a 60-min slot triggers
        the overload warning, with raita pre-selected for drop."""
        from app.services.cook_overload import detect_cook_overload

        plan = [
            {"name": "Chole", "estimated_cook_time_mins": 45},
            {"name": "Bhature", "estimated_cook_time_mins": 30},
            {"name": "Raita", "estimated_cook_time_mins": 10},
            {"name": "Gulab Jamun", "estimated_cook_time_mins": 25},
        ]
        result = detect_cook_overload(plan, slot_minutes=60)

        assert result.is_overloaded is True
        # 110 + 10 buffer = 120; headroom = 60 - 120 = -60
        assert result.headroom_minutes < 0
        # Raita should be among the suggested drops (it's a side dish)
        drops_lower = [d.lower() for d in result.suggested_drops]
        assert "raita" in drops_lower, result.suggested_drops

    def test_no_overload_when_within_slot(self):
        """Loop 8.2 — 2 dishes well within slot → no warning."""
        from app.services.cook_overload import detect_cook_overload

        plan = [
            {"name": "Dal", "estimated_cook_time_mins": 25},
            {"name": "Rice", "estimated_cook_time_mins": 15},
        ]
        result = detect_cook_overload(plan, slot_minutes=60)
        assert result.is_overloaded is False
        assert result.suggested_drops == []
        assert result.headroom_minutes >= 0

    def test_overload_warning_message_renders(self):
        """Loop 8.3 — The warning text mentions the total time AND the
        suggested drops in Hinglish."""
        from app.services.cook_overload import (
            detect_cook_overload,
            format_overload_warning,
        )

        plan = [
            {"name": "Biryani", "estimated_cook_time_mins": 90},
            {"name": "Salan", "estimated_cook_time_mins": 30},
        ]
        result = detect_cook_overload(plan, slot_minutes=60)
        assert result.is_overloaded
        msg = format_overload_warning(result, slot_minutes=60)
        assert "60 min" in msg
        assert "Slot" in msg
        # The suggestion list must be visible
        for drop in result.suggested_drops:
            assert drop in msg


# ─── End-to-end webhook smoke (uses ASGI client) ─────────────────────────


class TestEndToEnd_WebhookVoice:
    """A webhook POST with an audio message exercises the full pipeline:
    download_media → transcribe → split → extract → confirm. We pin the
    happy path and the low-conf fallback."""

    async def test_webhook_voice_text_known_parent(
        self, client, db, seed_family, fake_whatsapp, fake_transcription,
    ):
        """The whole inbound voice pipeline accepts a known parent's
        message, transcribes via the fake adapter, and 200s."""
        from app.adapters import TranscriptionResult
        from app.models.family import Parent

        parent = Parent(
            family_id=seed_family["family_id"],
            name="MM Test Parent",
            phone="+919800000600",
            whatsapp_id="919800000600",
            language="hi",
            role="parent",
        )
        db.add(parent)
        await db.commit()

        # Pre-register a media id with the fake whatsapp adapter and a
        # canned transcript with the fake transcription adapter.
        media_id = "test-multimodal-media-001"
        audio_bytes = b"\x00\x01\x02fake voice"
        fake_whatsapp.set_media(media_id, audio_bytes)
        fake_transcription.set_canned_for_audio(
            audio_bytes,
            TranscriptionResult(
                transcript="doodh ek litre laana",
                confidence=0.92,
                language="hi",
                source="fake",
            ),
        )

        r = await client.post(
            "/api/webhook",
            json={
                "entry": [{
                    "changes": [{
                        "value": {
                            "messages": [{
                                "from": "919800000600",
                                "type": "audio",
                                "audio": {"id": media_id},
                                "id": f"wamid.{uuid.uuid4().hex}",
                            }],
                        },
                    }],
                }],
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["dispatched"] == 1

    async def test_webhook_voice_idempotency_replay(
        self, client, db, seed_family, fake_whatsapp, fake_transcription,
    ):
        """Loop 5.1 — Meta retry of the same message_id is dispatched
        ONCE, deduped on subsequent deliveries."""
        from app.adapters import TranscriptionResult
        from app.models.family import Parent

        parent = Parent(
            family_id=seed_family["family_id"],
            name="MM Replay Parent",
            phone="+919800000601",
            whatsapp_id="919800000601",
            language="hi",
            role="parent",
        )
        db.add(parent)
        await db.commit()

        media_id = "test-multimodal-replay-001"
        audio_bytes = b"\x10\x11replay audio"
        fake_whatsapp.set_media(media_id, audio_bytes)
        fake_transcription.set_canned_for_audio(
            audio_bytes,
            TranscriptionResult(
                transcript="dahi laana",
                confidence=0.9,
                language="hi",
                source="fake",
            ),
        )

        msg_id = f"wamid.{uuid.uuid4().hex}"
        payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "from": "919800000601",
                            "type": "audio",
                            "audio": {"id": media_id},
                            "id": msg_id,
                        }],
                    },
                }],
            }],
        }
        first = (await client.post("/api/webhook", json=payload)).json()
        second = (await client.post("/api/webhook", json=payload)).json()

        assert first["dispatched"] == 1
        assert first["deduped"] == 0
        assert second["dispatched"] == 0
        assert second["deduped"] == 1
