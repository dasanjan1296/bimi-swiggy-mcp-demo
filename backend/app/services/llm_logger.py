"""Wrap every OpenAI chat-completion call so we get a row in `llm_calls`.

Why: H0 of the pilot AI plan. We had ~7 GPT-4o services running with no
observability. This is the seam through which every service now passes so
we can:

  - rebuild any prompt/response pair from the eval harness
  - track latency p50/p95 per service per cohort
  - attribute cost per family (kpi_aggregator reads `cost_usd`)
  - detect silent regressions when a prompt changes
  - feed prompt/response pairs as training rows for the H2 recommender

Design:
  - The wrapper NEVER raises. If logging fails, the LLM result still flows.
  - Logging is fire-and-forget via a session that commits and closes.
  - PII scrubbing reuses the analytics scrubber so the rules stay consistent.
  - Cost estimates are best-effort using a small price table; we can update
    rates without redeploying by editing PRICE_USD_PER_1K.

Two integration patterns:

  1. **Wrapper (preferred for new code)**: `await chat_completion(...)`
     does the call AND logs.

  2. **Manual log (for existing services that want minimal diff)**:
     `await log_call(service=..., ...)` from inside an existing httpx call
     site. Used to retrofit `intent.py`, `meal_engine.py`, etc. without
     rewriting their try/except scaffolding.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
import uuid
from typing import Any

import httpx

from app.config import settings
from app.db import async_session
from app.models.family import Family
from app.models.llm_call import LLMCall, LLMService

logger = logging.getLogger(__name__)

def chat_url() -> str:
    """OpenAI-compatible chat-completion URL. Reads settings every call so an
    .env change is picked up without restarting workers."""
    return f"{settings.openai_base_url.rstrip('/')}/chat/completions"


def embed_url() -> str:
    return f"{settings.openai_base_url.rstrip('/')}/embeddings"


def embed_dim() -> int:
    return int(settings.openai_embedding_dim)

# ---------------------------------------------------------------------------
# Cost table (USD per 1K tokens). Values from OpenAI public pricing as of
# 2026-04. Keep this small and update inline when prices change. We do NOT
# need this to be perfect -- it's for cost attribution, not billing.
# ---------------------------------------------------------------------------
PRICE_USD_PER_1K = {
    "gpt-4o":             {"prompt": 0.0025, "completion": 0.01},
    "gpt-4o-mini":        {"prompt": 0.00015, "completion": 0.0006},
    "text-embedding-3-small": {"prompt": 0.00002, "completion": 0.0},
    "text-embedding-3-large": {"prompt": 0.00013, "completion": 0.0},
}

EXCERPT_CHARS = 280


# ---------------------------------------------------------------------------
# PII scrub (keep aligned with analytics._scrub_pii but operates on text)
# ---------------------------------------------------------------------------

_PHONE_RE = re.compile(r"\+?\d[\d\s\-]{7,}")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# Aadhaar-shape: 12 contiguous digits. We err on the side of scrubbing.
_AADHAAR_RE = re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")


def _scrub_text(text: str | None) -> str | None:
    """Redact phone-shaped, email-shaped, and Aadhaar-shaped substrings."""
    if not text:
        return text
    text = _AADHAAR_RE.sub("<aadhaar>", text)
    text = _PHONE_RE.sub("<phone>", text)
    text = _EMAIL_RE.sub("<email>", text)
    return text


def _hash_prompt(prompt: str) -> str:
    """SHA-256 of the raw prompt -- the eval harness joins on this."""
    return hashlib.sha256(prompt.encode("utf-8", errors="ignore")).hexdigest()


def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float | None:
    """Best-effort cost in USD. Returns None for unknown models."""
    rates = PRICE_USD_PER_1K.get(model)
    if not rates:
        return None
    return round(
        (prompt_tokens / 1000.0) * rates["prompt"]
        + (completion_tokens / 1000.0) * rates["completion"],
        6,
    )


async def _resolve_cohort(family_id: uuid.UUID | None) -> str | None:
    """Cheap cohort lookup. Returns None on any error."""
    if family_id is None:
        return None
    try:
        async with async_session() as db:
            family = await db.get(Family, family_id)
            return family.cohort if family else None
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def log_call(
    *,
    service: str,
    model: str,
    prompt: str,
    response: str | None,
    latency_ms: int,
    family_id: uuid.UUID | None = None,
    cohort: str | None = None,
    ab_arm: str | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    success: bool = True,
    error: str | None = None,
    metadata: dict[str, Any] | None = None,
    provider: str = "openai",
) -> None:
    """Log one LLM call to the `llm_calls` table.

    Never raises. Safe to call from inside an existing service's happy path
    or its except branch.
    """
    try:
        if cohort is None:
            cohort = await _resolve_cohort(family_id)

        total = (prompt_tokens or 0) + (completion_tokens or 0) or None
        cost = (
            _estimate_cost(model, prompt_tokens, completion_tokens)
            if prompt_tokens is not None and completion_tokens is not None
            else None
        )

        row = LLMCall(
            id=uuid.uuid4(),
            service=service,
            model=model,
            provider=provider,
            family_id=family_id,
            cohort=cohort,
            ab_arm=ab_arm,
            prompt_hash=_hash_prompt(prompt),
            prompt_excerpt=(_scrub_text(prompt) or "")[:EXCERPT_CHARS],
            response_excerpt=(_scrub_text(response) or "")[:EXCERPT_CHARS] if response else None,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total,
            cost_usd=cost,
            latency_ms=latency_ms,
            success=success,
            error=(error or "")[:500] if error else None,
            metadata_json=metadata,
        )

        async with async_session() as db:
            db.add(row)
            await db.commit()
    except Exception:  # noqa: BLE001
        # Logging failure must NEVER take down the LLM call site.
        logger.exception("log_call(%s) failed -- dropping observability row", service)


async def chat_completion(
    *,
    service: str,
    messages: list[dict[str, Any]],
    family_id: uuid.UUID | None = None,
    ab_arm: str | None = None,
    temperature: float = 0.3,
    response_format: dict[str, Any] | None = None,
    timeout: float = 30.0,
    model: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Drop-in replacement for direct OpenAI chat-completion calls.

    Returns the parsed JSON response dict. Logs the call as a side effect.
    Raises on HTTP errors so the caller can decide how to handle.
    """
    chosen_model = model or settings.openai_model
    payload: dict[str, Any] = {
        "model": chosen_model,
        "messages": messages,
        "temperature": temperature,
    }
    if response_format:
        # Local LLMs (Ollama) don't always honour response_format=json_object,
        # but they ignore unknown keys; we pass it through unconditionally.
        payload["response_format"] = response_format

    # Build a single prompt string for hashing/excerpt. We concatenate role+content;
    # this is good enough for dedupe + debugging.
    prompt_str = "\n".join(f"[{m.get('role','?')}] {m.get('content','')}" for m in messages)

    started = time.perf_counter()
    success = True
    error_str: str | None = None
    response_text: str | None = None
    prompt_tokens = completion_tokens = None
    data: dict[str, Any] = {}

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                chat_url(),
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            response_text = data.get("choices", [{}])[0].get("message", {}).get("content")
            usage = data.get("usage", {}) or {}
            prompt_tokens = usage.get("prompt_tokens")
            completion_tokens = usage.get("completion_tokens")
        return data
    except Exception as exc:  # noqa: BLE001
        success = False
        error_str = repr(exc)[:500]
        raise
    finally:
        latency_ms = int((time.perf_counter() - started) * 1000)
        await log_call(
            service=service,
            model=chosen_model,
            prompt=prompt_str,
            response=response_text,
            latency_ms=latency_ms,
            family_id=family_id,
            ab_arm=ab_arm,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            success=success,
            error=error_str,
            metadata=metadata,
            provider=settings.llm_provider_label,
        )


async def embed(
    *,
    texts: list[str],
    family_id: uuid.UUID | None = None,
    model: str | None = None,
    timeout: float = 60.0,
) -> list[list[float]]:
    """Batch-embed a list of texts. Logs to `llm_calls`. Returns one vector per input.

    Falls back to deterministic hashed pseudo-embeddings of length
    `settings.openai_embedding_dim` if no API key is set, so dev/test
    environments don't need a billable key. The hash-based fallback is
    NOT useful for cosine similarity but lets schema validation + plumbing
    smoke tests run.
    """
    chosen_model = model or settings.openai_embedding_model
    dim = embed_dim()
    if not texts:
        return []
    if not settings.openai_api_key:
        return [_hashed_pseudo_embedding(t, dim) for t in texts]

    started = time.perf_counter()
    success = True
    error_str: str | None = None
    vectors: list[list[float]] = []
    prompt_tokens: int | None = None

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            # Some local OpenAI-compatible servers (Ollama at /v1/embeddings)
            # accept the same payload shape as OpenAI; some require one
            # request per input. Try batch first, fall back to per-input.
            try:
                resp = await client.post(
                    embed_url(),
                    headers={
                        "Authorization": f"Bearer {settings.openai_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={"model": chosen_model, "input": texts},
                )
                resp.raise_for_status()
                data = resp.json()
                vectors = [item["embedding"] for item in data.get("data", [])]
                usage = data.get("usage", {}) or {}
                prompt_tokens = usage.get("prompt_tokens")
            except Exception:
                # Per-input fallback for servers that don't support array input.
                vectors = []
                for t in texts:
                    r = await client.post(
                        embed_url(),
                        headers={
                            "Authorization": f"Bearer {settings.openai_api_key}",
                            "Content-Type": "application/json",
                        },
                        json={"model": chosen_model, "input": t},
                    )
                    r.raise_for_status()
                    rd = r.json()
                    if rd.get("data"):
                        vectors.append(rd["data"][0]["embedding"])
                    else:
                        vectors.append([0.0] * dim)
        # Defensive: enforce uniform dim. If the provider returned a different
        # length, truncate/pad so downstream cosine() comparisons don't break.
        vectors = [_to_dim(v, dim) for v in vectors]
        return vectors
    except Exception as exc:  # noqa: BLE001
        success = False
        error_str = repr(exc)[:500]
        return [_hashed_pseudo_embedding(t, dim) for t in texts]
    finally:
        latency_ms = int((time.perf_counter() - started) * 1000)
        await log_call(
            service=LLMService.EMBEDDING.value,
            model=chosen_model,
            prompt=f"<{len(texts)} text inputs, {sum(len(t) for t in texts)} chars>",
            response=f"<{len(vectors)} vectors>",
            latency_ms=latency_ms,
            family_id=family_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=0,
            success=success,
            error=error_str,
            provider=settings.llm_provider_label,
        )


def _to_dim(v: list[float], dim: int) -> list[float]:
    """Pad with zeros or truncate so the vector matches `dim` exactly."""
    if len(v) == dim:
        return v
    if len(v) > dim:
        return v[:dim]
    return list(v) + [0.0] * (dim - len(v))


def _hashed_pseudo_embedding(text: str, dim: int) -> list[float]:
    """Deterministic but not-actually-useful embedding for offline tests.

    Uses repeated SHA-256 of the text to fill `dim` floats in [-1, 1]. The
    important property is determinism (same text -> same vector) so cached
    results round-trip across test runs. Cosine similarity over these
    vectors is *not* semantically meaningful -- only structural plumbing
    is exercised in this fallback path.
    """
    out: list[float] = []
    seed = text.encode("utf-8", errors="ignore")
    counter = 0
    while len(out) < dim:
        h = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
        for i in range(0, len(h), 2):
            if len(out) >= dim:
                break
            val = int.from_bytes(h[i : i + 2], "big") / 65535.0  # 0..1
            out.append(val * 2 - 1)  # -1..1
        counter += 1
    return out
