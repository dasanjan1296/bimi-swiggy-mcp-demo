"""Health endpoints — split into liveness vs readiness.

`/health` (liveness):
  - "Am I alive?" — used by Render's container healthcheck.
  - Cheap. Just confirms the process is running.

`/health/ready` (readiness):
  - "Should I receive traffic?" — used by load balancers and during
    deploy rollouts.
  - Validates DB connectivity AND that production secrets are wired.
  - Returns 503 (Service Unavailable) on any failure so the platform
    can hold traffic at the previous green replica.

Both endpoints are skipped by `RateLimitMiddleware`
(see `_SKIP_RATE_LIMIT_PATHS` in `app/middleware.py`).

A non-200 from `/health/ready` does NOT crash the process — Render's
deploy will simply not mark the new replica healthy and traffic stays
on the old one.
"""

import logging

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.config import settings
from app.db import async_session

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/health")
async def health_check():
    """Liveness — returns 200 if the process is up.

    DB hiccup → status="degraded" but still 200 (we want the platform
    to NOT replace the container; traffic keeps flowing while a brief
    DB blip resolves).
    """
    checks = {"service": "bimi", "status": "ok"}
    try:
        async with async_session() as db:
            await db.execute(text("SELECT 1"))
        checks["database"] = "connected"
    except Exception as e:
        logger.warning("Health check DB failure: %s", e)
        checks["database"] = "unavailable"
        checks["status"] = "degraded"
    return checks


@router.get("/health/ready")
async def readiness_check(response: Response):
    """Readiness — full dependency check.

    Reports each dependency status individually. Returns 503 when any
    REQUIRED dependency fails so the platform doesn't route traffic
    to a half-configured replica.
    """
    checks: dict[str, object] = {
        "service": "bimi",
        "env": settings.bimi_env,
    }
    failed: list[str] = []

    # ── Postgres ────────────────────────────────────────────────────
    try:
        async with async_session() as db:
            await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["database"] = f"fail: {exc.__class__.__name__}"
        failed.append("database")

    # ── Required adapter credentials in production ─────────────────
    if settings.is_production:
        if not settings.openai_api_key:
            failed.append("openai_credentials")
            checks["openai"] = "missing"
        else:
            checks["openai"] = "configured"

        if not (settings.whatsapp_token and settings.whatsapp_phone_number_id
                and settings.whatsapp_app_secret):
            failed.append("whatsapp_credentials")
            checks["whatsapp"] = "missing"
        else:
            checks["whatsapp"] = "configured"

        if settings.whatsapp_verify_token == "bimi-verify":
            failed.append("whatsapp_verify_token_unrotated")
            checks["whatsapp_verify_token"] = "default-not-rotated"
    else:
        checks["openai"] = "configured" if settings.openai_api_key else "missing (dev)"
        checks["whatsapp"] = "configured" if settings.use_real_whatsapp else "missing (dev)"

    # ── Optional adapters (always informational) ───────────────────
    checks["sarvam_stt"] = "configured" if settings.sarvam_api_key else "missing"
    checks["voice_tts_enabled"] = settings.use_real_voice_replies
    checks["sentry"] = "enabled" if settings.sentry_dsn else "disabled"

    if failed:
        checks["status"] = "not_ready"
        checks["failed"] = failed
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return checks

    checks["status"] = "ready"
    return checks
