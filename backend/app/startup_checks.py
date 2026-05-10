"""Startup validation — crash early with clear messages.

Two modes:

1. **Development / staging / test**: log warnings for missing creds, keep
   running in demo mode. This lets contributors clone + start without
   needing every API key.

2. **Production** (`BIMI_ENV=production`): hard-fail on missing required
   credentials. A silently-broken prod deploy where Bimi can't talk to
   OpenAI / Meta / signature-verify is worse than an obvious crash —
   the alarm fires, you fix it, you redeploy.
"""
import logging
import sys

from app.config import settings

logger = logging.getLogger(__name__)


# Required in production. Each entry is (env_var_name, settings_attr,
# why_we_need_it). Missing → exit(1).
_PRODUCTION_REQUIRED: tuple[tuple[str, str, str], ...] = (
    ("OPENAI_API_KEY", "openai_api_key",
     "intent extraction + meal suggestions"),
    ("WHATSAPP_TOKEN", "whatsapp_token",
     "outbound WhatsApp messaging"),
    ("WHATSAPP_PHONE_NUMBER_ID", "whatsapp_phone_number_id",
     "outbound WhatsApp routing"),
    ("WHATSAPP_APP_SECRET", "whatsapp_app_secret",
     "webhook signature verification — without this, anyone can forge inbound messages"),
    ("WHATSAPP_VERIFY_TOKEN", "whatsapp_verify_token",
     "webhook GET-handshake against Meta"),
)


def validate_environment() -> None:
    """Check required env vars at startup.

    In production, missing required credentials cause a hard exit so
    the deploy fails fast (and the platform's healthcheck rolls back
    to the previous image). Outside production, missing credentials
    log warnings and the service runs in demo mode.
    """
    errors: list[str] = []
    warnings: list[str] = []

    if settings.is_production:
        for env_name, attr, reason in _PRODUCTION_REQUIRED:
            if not getattr(settings, attr, None):
                errors.append(f"{env_name} is required in production ({reason})")
        # The default verify-token value `bimi-verify` is documented in
        # the public repo. In production we MUST rotate it.
        if settings.whatsapp_verify_token == "bimi-verify":
            errors.append(
                "WHATSAPP_VERIFY_TOKEN is still the default 'bimi-verify' in "
                "production — anyone reading the repo can spoof Meta's webhook "
                "verify handshake. Rotate to a token from `secrets.token_urlsafe(24)`."
            )
        if settings.database_url.startswith("sqlite"):
            errors.append("DATABASE_URL points at SQLite — production requires PostgreSQL")
    else:
        if not settings.openai_api_key:
            warnings.append("OPENAI_API_KEY not set — running in MOCK AI mode")
        if not settings.whatsapp_token:
            warnings.append("WHATSAPP_TOKEN not set — outbound WhatsApp disabled")
        if not settings.whatsapp_phone_number_id:
            warnings.append("WHATSAPP_PHONE_NUMBER_ID not set — outbound WhatsApp disabled")
        if not settings.whatsapp_app_secret:
            warnings.append("WHATSAPP_APP_SECRET not set — webhook signature checks bypass in dev")

    if not settings.sarvam_api_key:
        warnings.append("SARVAM_API_KEY not set — Hindi voice transcription will use Whisper fallback")

    if not settings.swiggy_mcp_auth_token:
        warnings.append("SWIGGY_MCP_AUTH_TOKEN not set — Swiggy auto-ordering disabled (deep links only)")

    for w in warnings:
        logger.warning("CONFIG: %s", w)

    if errors:
        for e in errors:
            logger.error("FATAL: %s", e)
        if settings.is_production:
            # In production, refuse to come up. Render / k8s healthchecks
            # will then roll back to the previous green image.
            print(
                "FATAL: production startup checks failed. See errors above. "
                "Refusing to start.",
                file=sys.stderr,
            )
            sys.exit(1)
        else:
            logger.warning("Running in DEMO MODE — some features will not work")
