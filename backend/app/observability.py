"""Sentry integration — env-gated init.

Two design rules:

1. **No SENTRY_DSN ⇒ no Sentry.** The init is a no-op so dev/test
   environments don't have to think about it.

2. **Production gets sane defaults**: 10% trace sample, no profiling
   (profiling is not free in CPU). Override via env vars if needed.

The init runs once at startup (called from `main.py:lifespan`).
The FastAPI integration is auto-wired by sentry-sdk when present —
it captures unhandled exceptions, request context, and the
`X-Request-ID` header set by `RequestIDMiddleware`.

PII handling: we set `send_default_pii=False`. WhatsApp phone numbers
and message bodies should NEVER appear in error reports — those rows
are PII. If you need to debug a specific message, look at the local
log line tagged with the same request_id.
"""

from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger("bimi.observability")


_initialized = False


def init_sentry() -> bool:
    """Initialise the Sentry SDK if a DSN is configured.

    Returns True if Sentry is now active, False otherwise.
    """
    global _initialized

    if _initialized:
        return True
    if not settings.sentry_dsn:
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.asyncio import AsyncioIntegration
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
    except ImportError:
        logger.warning(
            "SENTRY_DSN is set but sentry-sdk is not installed. "
            "Run `pip install -r requirements.txt`.",
        )
        return False

    environment = settings.sentry_environment or settings.bimi_env

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        profiles_sample_rate=settings.sentry_profiles_sample_rate,
        # Phone numbers, message bodies, OTPs — never. Use logger
        # context (request_id) to correlate locally instead.
        send_default_pii=False,
        integrations=[
            FastApiIntegration(),
            StarletteIntegration(),
            SqlalchemyIntegration(),
            AsyncioIntegration(),
            # Capture WARN+ as breadcrumbs, ERROR+ as events.
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
        # Drop noisy events:
        before_send=_filter_event,
    )
    _initialized = True
    logger.info(
        "Sentry initialised (env=%s, traces=%.2f, profiles=%.2f)",
        environment,
        settings.sentry_traces_sample_rate,
        settings.sentry_profiles_sample_rate,
    )
    return True


def _filter_event(event: dict, hint: dict) -> dict | None:
    """Drop known-noisy events before they hit Sentry's quota.

    - 4xx HTTPExceptions are user errors, not system errors.
    - Cancelled tasks during shutdown are expected.
    - Rate-limit 429s are observable elsewhere (logs).
    """
    exc = (hint or {}).get("exc_info")
    if exc:
        exc_type = exc[0]
        exc_name = getattr(exc_type, "__name__", "")
        # FastAPI HTTPException with a 4xx status is user error
        if exc_name == "HTTPException":
            status = getattr(exc[1], "status_code", 500)
            if 400 <= status < 500:
                return None
        if exc_name in ("CancelledError", "ClientDisconnect"):
            return None
    return event
