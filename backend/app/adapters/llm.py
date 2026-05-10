"""LLM adapter — OpenAI in production, Fake everywhere else.

The pattern follows `app/adapters/otp.py`:

  - `LLMAdapter`   : Protocol for what every implementation must support
  - `OpenAIAdapter` : real OpenAI HTTP client (gpt-4o by default)
  - `FakeLLMAdapter`: deterministic fake that records calls + returns canned
                     responses keyed by call type — tests assert against the
                     recorded calls instead of mocking httpx
  - `get_llm_adapter()`: lru-cached factory that returns the right impl
                       based on `settings.use_real_ai`. Tests can swap in a
                       fake via `dependency_overrides` or `set_llm_adapter()`.

Production gate: the real OpenAI adapter is *only* returned when
`settings.use_real_ai` is True (i.e. `OPENAI_API_KEY` is set). Otherwise
the fake is returned, even in production — so a missing key fails closed
to deterministic stubs rather than silently breaking.

Every call site should record its call via `app.services.llm_logger`
(handled in the existing logger middleware); this adapter focuses purely
on the request/response.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol

import httpx

from app.config import settings

logger = logging.getLogger("bimi.llm.adapter")


# ─── Protocol ────────────────────────────────────────────────────────────────


@dataclass
class LLMResponse:
    """Structured wrapper around an LLM completion."""

    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    finish_reason: str = "stop"
    raw: dict | None = None
    json_payload: dict | list | None = None  # populated when response_format=json


class LLMAdapter(Protocol):
    """Single chat-completion entry point.

    Implementations MUST return an `LLMResponse` and SHOULD never raise on
    upstream API errors — log and return an `LLMResponse(text="", finish_reason="error")`
    so callers can degrade gracefully instead of 500-ing.
    """

    async def complete(
        self,
        *,
        prompt: str,
        system: str | None = None,
        model: str | None = None,
        max_tokens: int = 800,
        temperature: float = 0.4,
        response_format: str | None = None,  # "json" or None
        service: str = "other",
    ) -> LLMResponse: ...


# ─── Real ────────────────────────────────────────────────────────────────────


class OpenAIAdapter:
    """OpenAI chat completions over HTTPS. Uses the configured `openai_model`
    (default `gpt-4o`) and respects `response_format={"type":"json_object"}`
    when callers request JSON output."""

    OPENAI_URL = "https://api.openai.com/v1/chat/completions"
    DEFAULT_TIMEOUT = httpx.Timeout(60.0, connect=10.0)

    async def complete(
        self,
        *,
        prompt: str,
        system: str | None = None,
        model: str | None = None,
        max_tokens: int = 800,
        temperature: float = 0.4,
        response_format: str | None = None,
        service: str = "other",
    ) -> LLMResponse:
        if not settings.use_real_ai:
            logger.error(
                "OpenAIAdapter called without OPENAI_API_KEY — refusing. "
                "service=%s",
                service,
            )
            return LLMResponse(text="", model=model or settings.openai_model, finish_reason="error")

        chosen_model = model or settings.openai_model
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        body: dict[str, Any] = {
            "model": chosen_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if response_format == "json":
            body["response_format"] = {"type": "json_object"}

        # Loop 12: retry on transient 5xx + connection errors. OpenAI's
        # SLA is ~99.5% which means ~1 in 200 user-blocking calls would
        # fail without retry. Single-shot retry with a 1s backoff covers
        # most transient failures without significantly extending tail
        # latency.
        _RETRYABLE_STATUSES = (500, 502, 503, 504, 529)
        _MAX_ATTEMPTS = 2
        backoff_sec = 1.0

        resp = None
        last_exc: Exception | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                async with httpx.AsyncClient(timeout=self.DEFAULT_TIMEOUT) as client:
                    resp = await client.post(
                        self.OPENAI_URL,
                        headers={
                            "Authorization": f"Bearer {settings.openai_api_key}",
                            "Content-Type": "application/json",
                        },
                        json=body,
                    )
                if resp.status_code not in _RETRYABLE_STATUSES:
                    break
                if attempt + 1 < _MAX_ATTEMPTS:
                    logger.warning(
                        "OpenAI HTTP %s on attempt %d for service=%s — "
                        "retrying in %.1fs",
                        resp.status_code, attempt + 1, service, backoff_sec,
                    )
                    import asyncio
                    await asyncio.sleep(backoff_sec)
            except (httpx.ConnectError, httpx.ReadTimeout) as exc:
                last_exc = exc
                if attempt + 1 < _MAX_ATTEMPTS:
                    logger.warning(
                        "OpenAI transport error on attempt %d for service=%s: "
                        "%s — retrying in %.1fs",
                        attempt + 1, service, exc, backoff_sec,
                    )
                    import asyncio
                    await asyncio.sleep(backoff_sec)
                else:
                    last_exc = exc
            except httpx.HTTPError as exc:
                logger.error("OpenAI request failed for service=%s: %s", service, exc)
                return LLMResponse(text="", model=chosen_model, finish_reason="error")

        if resp is None:
            logger.error("OpenAI exhausted retries for service=%s: %s", service, last_exc)
            return LLMResponse(text="", model=chosen_model, finish_reason="error")
        if resp.status_code != 200:
            logger.error(
                "OpenAI HTTP %s for service=%s after retries: %s",
                resp.status_code, service, resp.text[:300],
            )
            return LLMResponse(text="", model=chosen_model, finish_reason="error")
        data = resp.json()

        choice = (data.get("choices") or [{}])[0]
        text = (choice.get("message") or {}).get("content") or ""
        usage = data.get("usage") or {}

        json_payload = None
        if response_format == "json":
            try:
                json_payload = json.loads(text)
            except (json.JSONDecodeError, ValueError):
                logger.warning(
                    "OpenAI returned non-JSON content despite response_format=json (service=%s)",
                    service,
                )

        return LLMResponse(
            text=text,
            model=chosen_model,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            finish_reason=choice.get("finish_reason", "stop"),
            raw=data,
            json_payload=json_payload,
        )


# ─── Fake ────────────────────────────────────────────────────────────────────


@dataclass
class _FakeCall:
    prompt: str
    system: str | None
    model: str
    response_format: str | None
    service: str


class FakeLLMAdapter:
    """Deterministic fake. Records every call; returns canned responses keyed
    by `service` (with overrides via `set_canned`).

    Default canned responses cover the `service` values the codebase currently
    uses (intent, meal_suggest, dish_infer, instruction, feedback, image,
    briefing, recap, twin, other). Each returns a minimal but well-formed
    structure so JSON-parsing callers don't crash.
    """

    DEFAULT_CANNED: dict[str, dict | list | str] = {
        "intent": {"intent": "unknown", "items": [], "confidence": 0.5},
        "meal_suggest": [
            {"dish": "Dal Tadka", "confidence": 0.8, "rationale": "household staple"},
            {"dish": "Jeera Rice", "confidence": 0.75, "rationale": "pairs with dal"},
        ],
        "dish_infer": {"dishes": ["Dal Tadka", "Jeera Rice"], "confidence": 0.7},
        "instruction": {
            "instruction_text": "Test instruction",
            "schedule": "daily",
            "structured_action": {},
        },
        "feedback": {"sentiment": "positive", "summary": "ok"},
        "image": {"product_name": "Atta", "brand": "Aashirvaad", "confidence": 0.7},
        "briefing": "Aaj ka brief: dal-rice for 4 people. Allergy alerts: none.",
        "recap": "Recap: 21 meals planned, 18 completed, avg rating 4.2.",
        "twin": "The household prefers mild spice and minimal oil.",
        "other": "ok",
    }

    def __init__(self) -> None:
        self.calls: list[_FakeCall] = []
        self._canned: dict[str, dict | list | str] = dict(self.DEFAULT_CANNED)

    async def complete(
        self,
        *,
        prompt: str,
        system: str | None = None,
        model: str | None = None,
        max_tokens: int = 800,
        temperature: float = 0.4,
        response_format: str | None = None,
        service: str = "other",
    ) -> LLMResponse:
        chosen_model = model or "fake-llm"
        self.calls.append(_FakeCall(
            prompt=prompt, system=system, model=chosen_model,
            response_format=response_format, service=service,
        ))
        canned = self._canned.get(service, self._canned["other"])

        if response_format == "json":
            text = json.dumps(canned) if isinstance(canned, (dict, list)) else json.dumps({"answer": canned})
            return LLMResponse(
                text=text,
                model=chosen_model,
                json_payload=canned if isinstance(canned, (dict, list)) else {"answer": canned},
            )

        text = canned if isinstance(canned, str) else json.dumps(canned)
        return LLMResponse(text=text, model=chosen_model)

    # ─── Test helpers ─────────────────────────────────────────────────────

    def set_canned(self, service: str, payload: dict | list | str) -> None:
        self._canned[service] = payload

    def reset(self) -> None:
        self.calls.clear()
        self._canned = dict(self.DEFAULT_CANNED)

    def calls_for(self, service: str) -> list[_FakeCall]:
        return [c for c in self.calls if c.service == service]


# ─── Factory ─────────────────────────────────────────────────────────────────


_override: LLMAdapter | None = None


@lru_cache(maxsize=1)
def _default_llm_adapter() -> LLMAdapter:
    if settings.use_real_ai:
        logger.info("LLM adapter: OpenAI (real)")
        return OpenAIAdapter()
    logger.info("LLM adapter: Fake (use_real_ai=False)")
    return FakeLLMAdapter()


def get_llm_adapter() -> LLMAdapter:
    """Return the LLM adapter. Honours `set_llm_adapter()` override (used by tests)."""
    if _override is not None:
        return _override
    return _default_llm_adapter()


def set_llm_adapter(adapter: LLMAdapter | None) -> None:
    """Install a custom adapter (typically a `FakeLLMAdapter` from a test)."""
    global _override
    _override = adapter


def reset_llm_adapter_cache() -> None:
    """Clear the lru_cache + override (call from teardown)."""
    global _override
    _override = None
    _default_llm_adapter.cache_clear()
