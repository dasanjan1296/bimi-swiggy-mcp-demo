"""WhatsApp adapter — Meta Cloud API in production, Fake everywhere else.

Wraps the three operations the app actually performs against the Meta
Cloud API:

  - `send_message(payload)` : low-level send for text/interactive/template
  - `download_media(media_id)` : pull a voice note / image binary

Everything `app/services/whatsapp.py` does is a higher-level helper that
ultimately funnels into these two methods (plus signature verification,
which is a pure function on bytes and lives in `main.verify_whatsapp_signature`).

In the FakeWhatsAppAdapter, every outbound message is recorded so tests can
assert against the conversation history without mocking httpx.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Protocol

import httpx

from app.config import settings

logger = logging.getLogger("bimi.whatsapp.adapter")

BASE_URL = "https://graph.facebook.com/v21.0"
DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


# ─── Protocol ────────────────────────────────────────────────────────────────


@dataclass
class WhatsAppSendResult:
    message_id: str | None = None
    raw: dict = field(default_factory=dict)


class WhatsAppAdapter(Protocol):
    """Minimal surface every WhatsApp implementation must support."""

    async def send_message(self, payload: dict) -> WhatsAppSendResult: ...

    async def download_media(self, media_id: str) -> bytes: ...


# ─── Real ────────────────────────────────────────────────────────────────────


class CloudApiWhatsAppAdapter:
    """Meta WhatsApp Cloud API client (graph.facebook.com)."""

    async def send_message(self, payload: dict) -> WhatsAppSendResult:
        if not settings.use_real_whatsapp:
            logger.error(
                "CloudApiWhatsAppAdapter called without WHATSAPP_TOKEN — refusing to send. "
                "to=%s type=%s",
                payload.get("to"), payload.get("type"),
            )
            return WhatsAppSendResult()

        # Loop 13 retry: Meta rate-limits us during spikes and returns 429
        # with `Retry-After` (seconds). Without retry, those messages are
        # silently dropped — user-visible breakage. We retry once after
        # waiting the requested interval (capped at 30s).
        import asyncio as _asyncio

        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                for attempt in range(2):
                    resp = await client.post(
                        f"{BASE_URL}/{settings.whatsapp_phone_number_id}/messages",
                        headers={
                            "Authorization": f"Bearer {settings.whatsapp_token}",
                            "Content-Type": "application/json",
                        },
                        json={"messaging_product": "whatsapp", **payload},
                    )
                    if resp.status_code != 429 or attempt > 0:
                        break
                    retry_after_raw = resp.headers.get("Retry-After", "1")
                    try:
                        retry_after = min(float(retry_after_raw), 30.0)
                    except (TypeError, ValueError):
                        retry_after = 1.0
                    logger.warning(
                        "WhatsApp 429 — sleeping %.1fs before retry (Retry-After=%r)",
                        retry_after, retry_after_raw,
                    )
                    await _asyncio.sleep(retry_after)
            if resp.status_code >= 400:
                logger.error(
                    "WhatsApp send failed (HTTP %s) to=%s: %s",
                    resp.status_code, payload.get("to"), resp.text[:300],
                )
                return WhatsAppSendResult()
            data = resp.json()
        except httpx.HTTPError as exc:
            logger.error("WhatsApp send error to=%s: %s", payload.get("to"), exc)
            return WhatsAppSendResult()

        msg_id = None
        if data.get("messages"):
            msg_id = data["messages"][0].get("id")
        return WhatsAppSendResult(message_id=msg_id, raw=data)

    async def download_media(self, media_id: str) -> bytes:
        """Download media with a 20 MB hard cap (Loop 15).

        The cap protects worker memory: a buggy or attacker-controlled
        redirect URL could otherwise serve gigabytes and OOM the box.
        Meta's documented audio/video max is 16 MB; we add headroom.
        """
        if not settings.use_real_whatsapp:
            logger.error("CloudApiWhatsAppAdapter.download_media called without WHATSAPP_TOKEN")
            return b""

        media_max_bytes = 20 * 1024 * 1024
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                url_resp = await client.get(
                    f"{BASE_URL}/{media_id}",
                    headers={"Authorization": f"Bearer {settings.whatsapp_token}"},
                )
                url_resp.raise_for_status()
                media_url = url_resp.json()["url"]

                async with client.stream(
                    "GET",
                    media_url,
                    headers={"Authorization": f"Bearer {settings.whatsapp_token}"},
                ) as media_resp:
                    media_resp.raise_for_status()
                    content_length = media_resp.headers.get("Content-Length")
                    if content_length and content_length.isdigit():
                        if int(content_length) > media_max_bytes:
                            logger.warning(
                                "WhatsApp media %s exceeds size cap "
                                "(Content-Length=%s, max=%d)",
                                media_id, content_length, media_max_bytes,
                            )
                            return b""
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in media_resp.aiter_bytes(chunk_size=64 * 1024):
                        total += len(chunk)
                        if total > media_max_bytes:
                            logger.warning(
                                "WhatsApp media %s exceeded cap mid-stream "
                                "(total=%d, max=%d)",
                                media_id, total, media_max_bytes,
                            )
                            return b""
                        chunks.append(chunk)
                    return b"".join(chunks)
        except httpx.HTTPError as exc:
            logger.error("WhatsApp media download failed for id=%s: %s", media_id, exc)
            return b""


# ─── Fake ────────────────────────────────────────────────────────────────────


@dataclass
class FakeMessage:
    to: str
    type: str
    payload: dict
    message_id: str

    def text(self) -> str | None:
        if self.type == "text":
            return (self.payload.get("text") or {}).get("body")
        return None

    def buttons(self) -> list[dict] | None:
        if self.type == "interactive":
            interactive = self.payload.get("interactive") or {}
            if interactive.get("type") == "button":
                return ((interactive.get("action") or {}).get("buttons")) or []
        return None


class FakeWhatsAppAdapter:
    """Records every outbound message + serves canned media downloads."""

    def __init__(self) -> None:
        self.sent: list[FakeMessage] = []
        self._media: dict[str, bytes] = {}
        self._next_id = 1

    async def send_message(self, payload: dict) -> WhatsAppSendResult:
        msg_id = f"wamid.fake.{self._next_id:06d}"
        self._next_id += 1
        self.sent.append(FakeMessage(
            to=payload.get("to", ""),
            type=payload.get("type", "text"),
            payload=payload,
            message_id=msg_id,
        ))
        return WhatsAppSendResult(message_id=msg_id, raw={"messages": [{"id": msg_id}]})

    async def download_media(self, media_id: str) -> bytes:
        return self._media.get(media_id, b"")

    # ─── Test helpers ─────────────────────────────────────────────────────

    def set_media(self, media_id: str, content: bytes) -> None:
        self._media[media_id] = content

    def messages_to(self, to: str) -> list[FakeMessage]:
        return [m for m in self.sent if m.to == to]

    def last(self) -> FakeMessage | None:
        return self.sent[-1] if self.sent else None

    def reset(self) -> None:
        self.sent.clear()
        self._media.clear()
        self._next_id = 1


# ─── Factory ─────────────────────────────────────────────────────────────────


_override: WhatsAppAdapter | None = None


@lru_cache(maxsize=1)
def _default_whatsapp_adapter() -> WhatsAppAdapter:
    if settings.use_real_whatsapp:
        logger.info("WhatsApp adapter: Meta Cloud API (real)")
        return CloudApiWhatsAppAdapter()
    logger.info("WhatsApp adapter: Fake (use_real_whatsapp=False)")
    return FakeWhatsAppAdapter()


def get_whatsapp_adapter() -> WhatsAppAdapter:
    if _override is not None:
        return _override
    return _default_whatsapp_adapter()


def set_whatsapp_adapter(adapter: WhatsAppAdapter | None) -> None:
    global _override
    _override = adapter


def reset_whatsapp_adapter_cache() -> None:
    global _override
    _override = None
    _default_whatsapp_adapter.cache_clear()
