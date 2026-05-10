import sys

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://bimi:bimi@localhost:5432/bimi"

    # WhatsApp Business API
    whatsapp_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_verify_token: str = "bimi-verify"
    whatsapp_app_secret: str = ""

    # AI services
    sarvam_api_key: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    # Swiggy MCP (Instamart + Food). Loop 5 will replace the bare token with
    # full OAuth: client_id / client_secret / redirect_uri.
    swiggy_mcp_auth_token: str = ""

    firebase_credentials_path: str = "firebase-service-account.json"

    # Founder ops alerts
    founder_phone: str = ""
    founder_alerts_enabled: bool = True

    # WhatsApp-native cook onboarding. When True (default), creating a
    # Parent row with role='cook' fires the welcome confirmation card
    # to the cook's WhatsApp number. Flip to False during a rollout to
    # silence the auto-greeting (the card can still be sent manually
    # via the /resend-onboarding endpoint).
    cook_onboarding_enabled: bool = True

    # OTP / AuthKey.io SMS
    authkey_api_key: str = ""
    authkey_template_sid: str = "30729"
    otp_expiry_seconds: int = 300

    secret_key: str = "change-me"
    frontend_url: str = "http://localhost:5173"

    # Deployment environment: development | staging | production
    # Used to gate developer affordances (dev_otp leak, demo Swiggy MCP fakes, etc.)
    bimi_env: str = "development"

    # Batching thresholds
    batch_min_amount: int = 300
    batch_max_wait_hours: int = 24
    batch_hard_max_days: int = 3

    # Rate-limit middleware budget (requests / minute / IP). Production runs
    # the conservative default; dev/test environments override via env so
    # full E2E suites — which can hammer the same IP with hundreds of
    # requests in seconds — don't false-positive on 429.
    rate_limit_per_minute: int = 600

    # Confidence thresholds
    confidence_high: float = 0.8
    confidence_medium: float = 0.5
    max_clarification_attempts: int = 3

    # Voice-out (TTS) for cook-facing replies. When True, the system emits
    # voice notes via Sarvam TTS in addition to text captions. When False
    # (default), voice replies degrade to text-only — still functional,
    # just without the voice delivery the cook prefers.
    use_real_voice_replies: bool = False
    # Below this transcript-confidence threshold we send the
    # best-guess fallback instead of running full extraction. See
    # docs/MULTIMODAL-VALIDATION-REPORT.md §2.1.
    voice_low_confidence_threshold: float = 0.45

    # Sentry — opt-in via env. Empty DSN disables Sentry entirely.
    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 0.1
    sentry_profiles_sample_rate: float = 0.0
    sentry_environment: str = ""  # falls back to bimi_env when blank

    @property
    def use_real_ai(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def use_real_whatsapp(self) -> bool:
        return bool(self.whatsapp_token)

    @property
    def can_mcp_order(self) -> bool:
        return bool(self.swiggy_mcp_auth_token)

    @property
    def use_real_sms(self) -> bool:
        return bool(self.authkey_api_key and self.authkey_template_sid)

    @property
    def is_production(self) -> bool:
        return self.bimi_env.lower() == "production"

    @property
    def is_development(self) -> bool:
        return self.bimi_env.lower() == "development"

    model_config = {"env_file": ".env", "extra": "ignore"}

    @model_validator(mode="after")
    def _enforce_production_hardening(self) -> "Settings":
        """In production, hard-fail on insecure defaults. We can't allow
        the deploy to come up with a forgeable JWT signing key — every
        access token would be trivially forgeable by anyone who reads
        the public source.

        Loop 11 strict-mode (replaces the previous heuristic that only
        exited when database_url was non-default — which let a real
        prod deploy with a real DB but forgotten SECRET_KEY boot fine,
        then quietly sign every JWT with `change-me`).
        """
        if self.bimi_env.lower() == "production" and self.secret_key == "change-me":
            print(
                "FATAL: SECRET_KEY is still 'change-me' in production. "
                "Refusing to start — every JWT would be forgeable.",
                file=sys.stderr,
            )
            print(
                "Generate one with: "
                "python -c \"import secrets; print(secrets.token_hex(32))\"",
                file=sys.stderr,
            )
            sys.exit(1)
        return self


settings = Settings()

if settings.secret_key == "change-me" and not settings.is_production:
    print(
        "WARNING: SECRET_KEY is 'change-me' (development only — must be "
        "changed before BIMI_ENV=production).",
        file=sys.stderr,
    )
