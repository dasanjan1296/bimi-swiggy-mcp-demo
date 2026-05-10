"""Bimi WhatsApp POC server.

A minimal FastAPI app that:
  1. Receives Evolution API webhooks at /webhook
  2. Recognises 5 demo intents and replies via the Evolution send API
  3. Differentiates group vs 1:1 chats
  4. Acts "human" — marks messages read, shows typing, delays responses
     before replying. Drops Meta's bot-detection heuristics dramatically.

Run with: `python server.py`
Requires: Evolution API container running + paired QR (see README.md).
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import re
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("bimi-poc")

# ── Config ──────────────────────────────────────────────────────────────────

EVOLUTION_URL = os.getenv("EVOLUTION_PUBLIC_URL", "http://localhost:8080")
EVOLUTION_KEY = os.getenv("EVOLUTION_API_KEY", "")
INSTANCE = os.getenv("EVOLUTION_INSTANCE", "bimi-poc")
PORT = int(os.getenv("POC_PORT", "9000"))

# Human-emulation tunables. Meta's 2026 bot detection flags accounts
# that reply in <500ms and never send presence updates. These windows
# match how a real person uses WhatsApp:
#   - read the message, take a beat (THINK_MIN..MAX)
#   - start typing, "compose" for a few seconds (TYPE_MIN..MAX)
#   - send. Total feels-like-a-human latency ≈ 2-6 seconds.
THINK_MIN_SEC = 0.6
THINK_MAX_SEC = 1.6
TYPE_MIN_SEC = 1.5
TYPE_MAX_SEC = 4.0

if not EVOLUTION_KEY:
    log.warning("EVOLUTION_API_KEY is empty — outbound calls will fail. Check .env")

# ── App ─────────────────────────────────────────────────────────────────────

app = FastAPI(title="Bimi WhatsApp POC")

# Tracks every inbound message we've seen this session — for the /history
# debug endpoint. Capped to last 100 to avoid memory bloat.
_history: list[dict] = []
_HISTORY_MAX = 100


# ── Outbound: send via Evolution API ────────────────────────────────────────


async def send_text(to_jid: str, text: str) -> dict:
    """Send a text message to a JID (1:1 user or group).

    Evolution accepts the JID in the `number` field — same endpoint
    works for `1234567890@s.whatsapp.net` (1:1) and `xxx@g.us` (group).
    """
    url = f"{EVOLUTION_URL}/message/sendText/{INSTANCE}"
    payload = {"number": to_jid, "text": text}
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            url,
            json=payload,
            headers={"apikey": EVOLUTION_KEY},
        )
    if resp.status_code >= 400:
        log.error("send_text failed → %s: %s", resp.status_code, resp.text[:300])
    else:
        log.info("→ %s | %s", to_jid, text[:80])
    return {"status": resp.status_code, "body": resp.text[:300]}


# ── Human-emulation helpers (anti-ban) ──────────────────────────────────────


async def mark_as_read(remote_jid: str, message_id: str, from_me: bool) -> None:
    """Send blue ticks for a received message.

    Meta's bot heuristics flag accounts that never read inbound messages
    — real users always trigger the read receipt before replying. Best
    effort: any failure is logged and swallowed.
    """
    url = f"{EVOLUTION_URL}/chat/markMessageAsRead/{INSTANCE}"
    payload = {
        "readMessages": [
            {"remoteJid": remote_jid, "fromMe": from_me, "id": message_id}
        ]
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                url, json=payload, headers={"apikey": EVOLUTION_KEY},
            )
        if resp.status_code >= 400:
            log.debug("mark_as_read non-200: %s %s", resp.status_code, resp.text[:120])
    except Exception:  # noqa: BLE001 — best-effort
        log.debug("mark_as_read failed", exc_info=True)


async def send_presence(to_jid: str, presence: str, *, hold_sec: float = 0.0) -> None:
    """Set our presence in a chat: 'composing' (typing), 'recording' (audio),
    or 'paused' (stopped typing).

    `hold_sec` keeps the indicator visible — Evolution's presence is
    sticky for ~30s but explicit hold is cleaner. Caller usually sends
    `composing` with hold matching the typing window, then sends the
    actual message which clears the indicator automatically.
    """
    url = f"{EVOLUTION_URL}/chat/sendPresence/{INSTANCE}"
    payload = {"number": to_jid, "presence": presence, "delay": int(hold_sec * 1000)}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                url, json=payload, headers={"apikey": EVOLUTION_KEY},
            )
        if resp.status_code >= 400:
            log.debug("send_presence non-200: %s %s", resp.status_code, resp.text[:120])
    except Exception:  # noqa: BLE001
        log.debug("send_presence failed", exc_info=True)


async def human_reply(
    *,
    to_jid: str,
    text: str,
    inbound_message_id: str | None,
    inbound_from_me: bool = False,
) -> dict:
    """Reply with the same cadence a real human would use.

    Sequence:
      1. Mark the inbound message as read (blue ticks)
      2. Pause briefly (THINK window) — like reading the message
      3. Send 'composing' presence (typing indicator)
      4. Hold the typing indicator for the TYPE window
      5. Send the actual message (clears the indicator)

    Total perceived latency: ~2-6 seconds. Tunable via the THINK_/TYPE_
    constants near the top of the file. Documented patterns and
    rationale in whatsapp/architecture/anti-ban-patterns.html.
    """
    if inbound_message_id:
        await mark_as_read(to_jid, inbound_message_id, inbound_from_me)

    think = random.uniform(THINK_MIN_SEC, THINK_MAX_SEC)
    await asyncio.sleep(think)

    type_for = random.uniform(TYPE_MIN_SEC, TYPE_MAX_SEC)
    await send_presence(to_jid, "composing", hold_sec=type_for)
    await asyncio.sleep(type_for)

    return await send_text(to_jid, text)


# ── Health + debug ──────────────────────────────────────────────────────────


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "evolution_url": EVOLUTION_URL,
        "instance": INSTANCE,
        "history_count": len(_history),
    }


@app.get("/history")
async def history():
    """Last 100 inbound messages — useful for debugging without scrolling logs."""
    return {"messages": _history}


@app.post("/send")
async def send_proactive(payload: dict):
    """Manual outbound — POST {to: "<jid>", text: "..."} to test sending."""
    return await send_text(payload["to"], payload["text"])


# ── Inbound: webhook from Evolution ─────────────────────────────────────────


@app.post("/webhook")
async def webhook(request: Request) -> dict:
    """Evolution POSTs every event here.

    We only act on inbound text messages (`messages.upsert` event,
    `key.fromMe == False`, `message.conversation` or
    `extendedTextMessage.text` populated).
    """
    body = await request.json()

    event = body.get("event", "")
    data = body.get("data", {}) or {}

    if event != "messages.upsert":
        log.debug("ignoring event: %s", event)
        return {"ok": True, "ignored": event}

    msg = _extract_message(data)
    if msg is None:
        return {"ok": True, "ignored": "unparseable"}

    if msg["from_me"]:
        return {"ok": True, "ignored": "fromMe"}

    _record(msg)
    log.info(
        "← %s [%s] %s: %s",
        "GRP" if msg["is_group"] else "1:1",
        msg["sender_label"],
        msg["push_name"] or "?",
        msg["text"][:80],
    )

    reply = _decide_reply(msg)
    if reply is not None:
        # Use human_reply (read receipt + typing presence + delay) so
        # Bimi looks like a person, not a bot. See architecture doc.
        await human_reply(
            to_jid=msg["reply_to"],
            text=reply,
            inbound_message_id=msg.get("message_id"),
            inbound_from_me=msg["from_me"],
        )

    return {"ok": True}


# ── Parser: Baileys-shaped payloads → flat dict ─────────────────────────────


def _extract_message(data: dict) -> dict | None:
    """Flatten Evolution's Baileys-style payload into the fields we care about.

    Evolution wraps Baileys; field paths are stable across v2.x but the
    text body lives in different sub-fields depending on message type.
    """
    key = data.get("key", {}) or {}
    message = data.get("message", {}) or {}

    remote_jid: str | None = key.get("remoteJid")
    if not remote_jid:
        return None

    is_group = remote_jid.endswith("@g.us")
    from_me = bool(key.get("fromMe", False))

    # In a group, the actual sender is `participant`; in 1:1 it's the JID itself.
    sender_jid = key.get("participant") if is_group else remote_jid

    # Text body — try all the places Baileys can stash it.
    text = (
        message.get("conversation")
        or (message.get("extendedTextMessage") or {}).get("text")
        or ""
    ).strip()

    return {
        "remote_jid": remote_jid,
        "is_group": is_group,
        "from_me": from_me,
        "sender_jid": sender_jid,
        "sender_label": (sender_jid or "").split("@", 1)[0] or "?",
        "push_name": data.get("pushName"),
        "text": text,
        # Replies always go to the same chat (group or 1:1) the message came from.
        "reply_to": remote_jid,
        # Inbound id — needed so we can mark this exact message as read.
        "message_id": key.get("id"),
    }


def _record(msg: dict) -> None:
    _history.append(msg)
    if len(_history) > _HISTORY_MAX:
        del _history[: len(_history) - _HISTORY_MAX]


# ── Demo intents ────────────────────────────────────────────────────────────

URL_RE = re.compile(r"https?://\S+")
MEAL_READY_RE = re.compile(r"\b(ban gay[ai]|ho gay[ai]|ready|tayyar)\b", re.IGNORECASE)


def _decide_reply(msg: dict) -> str | None:
    """Map an inbound message to a POC reply (or None to stay silent).

    Order matters — first match wins.
    """
    text = msg["text"]
    if not text:
        return None

    lower = text.lower().strip()
    chan = "[group]" if msg["is_group"] else "[1:1]"

    # 1. Help command
    if lower in ("bimi help", "help", "@bimi"):
        return _help_text(chan)

    # 2. Recipe link detection
    url_match = URL_RE.search(text)
    if url_match:
        return f"{chan} 🎬 Recipe link mil gaya: {url_match.group(0)}\n(POC: detected URL; in prod, oEmbed + dish-name resolution would run here)"

    # 3. "Khana ban gaya" — meal ready signal
    if MEAL_READY_RE.search(lower):
        return f"{chan} ✅ Khana ready! Sab logo ko bata diya. 🙏\n(POC: detected meal_ready intent)"

    # 4. Plain text echo (with channel tag for clarity during demo)
    return f"{chan} You said: {text!r}"


def _help_text(chan: str) -> str:
    return (
        f"{chan} Bimi POC — demo commands:\n\n"
        "1. Type anything → I echo it back tagged with [group] or [1:1]\n"
        "2. Share a YouTube/Instagram URL → I detect it as a recipe link\n"
        "3. Type 'khana ban gaya' / 'ready' → I confirm meal-ready\n"
        "4. Type 'bimi help' → you're seeing this :)\n\n"
        "POC server logs every inbound at GET /history."
    )


# ── Run ─────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    import uvicorn
    log.info("Bimi POC starting on :%d  (Evolution: %s)", PORT, EVOLUTION_URL)
    log.info("Webhook URL Evolution should POST to: http://host.docker.internal:%d/webhook", PORT)
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
