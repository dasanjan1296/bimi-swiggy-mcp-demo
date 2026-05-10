import hashlib
import hmac
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.logging_config import setup_logging
from app.middleware import (
    BodySizeLimitMiddleware,
    RateLimitMiddleware,
    RequestIDMiddleware,
)
from app.observability import init_sentry
from app.routers import (
    absences,
    approval,
    auto_rules,
    calls,
    context,
    dish_notes,
    expenses,
    family,
    grocery_baskets,
    guests,
    hcg,
    health,
    health_tracking,
    instructions,
    inventory,
    investor,
    leftovers,
    meal_history,
    meals,
    ordering,
    person_context,
    pilot,
    recipe_archive,
    recipes,
    saved_recipes,
    substitutions,
    swiggy_auth,
    voting,
    webhook,
    your_kitchen,
)
from app.startup_checks import validate_environment
from app.tasks.batcher import start_scheduler, stop_scheduler

setup_logging()
init_sentry()  # No-op when SENTRY_DSN is unset — safe to always call.
logger = logging.getLogger("bimi")


@asynccontextmanager
async def lifespan(app: FastAPI):
    import os

    validate_environment()
    logger.info("Bimi API starting — scheduler initializing")
    # NOTE: OTP table creation used to live here as a lazy CREATE IF NOT
    # EXISTS. Migration 042 now owns the schema, so we no longer touch the
    # DB at lifespan start. If you're upgrading an old DB that hasn't run
    # 042, run `alembic upgrade head` once.

    # The scheduler + analytics flusher both spin background tasks that
    # poll the DB. Tests don't want them running, so we honour the
    # `BIMI_DISABLE_SCHEDULER=1` escape hatch.
    scheduler_disabled = os.getenv("BIMI_DISABLE_SCHEDULER", "0") == "1"
    if scheduler_disabled:
        logger.info("Scheduler + analytics flusher DISABLED (BIMI_DISABLE_SCHEDULER=1)")
    else:
        start_scheduler()
        from app.services.analytics import start_flusher
        start_flusher()

    yield

    if not scheduler_disabled:
        from app.services.analytics import stop_flusher
        await stop_flusher()
        stop_scheduler()
    logger.info("Bimi API shut down")


# Loop 12: gate OpenAPI / Swagger / ReDoc in production. Anonymous schema
# enumeration helps attackers map our route surface and Pydantic field
# constraints. In dev/staging we keep them on for productivity. To re-
# enable docs in production, mount a reverse-proxy with auth in front of
# `/_internal/openapi.json` rather than re-exposing the public path.
_openapi_url = None if settings.is_production else "/openapi.json"
_docs_url = None if settings.is_production else "/docs"
_redoc_url = None if settings.is_production else "/redoc"

app = FastAPI(
    title="Bimi API",
    version="0.1.0",
    lifespan=lifespan,
    openapi_url=_openapi_url,
    docs_url=_docs_url,
    redoc_url=_redoc_url,
)

# Loop 14: CORS origins gated on environment. With `allow_credentials=True`,
# leaving `localhost:*` in production opens an XSRF surface for any user
# who has a localhost dev server running on those ports. In production the
# origin list is JUST the configured frontend URL.
def _cors_origins() -> list[str]:
    if settings.is_production:
        return [settings.frontend_url]
    return [
        settings.frontend_url,
        "http://localhost:5173",  # Vite dev server
        "http://localhost:8081",  # Expo web
        "http://localhost:19006",  # Expo web (legacy port)
    ]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    RateLimitMiddleware,
    # Loop-stability fix: configurable so E2E suites (and the local dev
    # cycle) can crank the budget up. Production keeps the default 600/min.
    requests_per_minute=settings.rate_limit_per_minute,
)
# Body size cap. WhatsApp media payloads are small (audio/text/image refs
# carry only IDs, not bytes — actual media is downloaded via separate
# /media/<id> calls). 1 MiB is generous for legit traffic but blocks
# DoS-style 100MB POSTs that would OOM the worker.
app.add_middleware(BodySizeLimitMiddleware, max_bytes=1 * 1024 * 1024)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


def verify_whatsapp_signature(payload: bytes, signature: str) -> bool:
    """
    Verify Meta's X-Hub-Signature-256 header on webhook requests.

    P5.1 fix: Meta signs the body with the App Secret, NOT the verify token
    (the verify token is only used for the initial GET handshake). Previously
    we were keying HMAC off the wrong secret, which silently passed every
    request. Now uses `whatsapp_app_secret`. Also: in production we fail
    closed when the secret is unset; in dev we still allow through for
    local testing without keys.
    """
    if not settings.whatsapp_app_secret:
        if settings.is_production:
            return False
        return True
    if not signature:
        return False
    expected = "sha256=" + hmac.new(
        settings.whatsapp_app_secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


app.include_router(health.router)
app.include_router(webhook.router, prefix="/api")
app.include_router(family.router, prefix="/api")
app.include_router(family.household_router, prefix="/api")
app.include_router(approval.router, prefix="/api")
app.include_router(context.router, prefix="/api")
app.include_router(inventory.router, prefix="/api")
app.include_router(inventory.router, prefix="/api/families/{family_id}", tags=["inventory-alias"])
app.include_router(meals.router, prefix="/api")
app.include_router(meal_history.router, prefix="/api")
app.include_router(absences.router, prefix="/api")
app.include_router(calls.router, prefix="/api")
app.include_router(person_context.router, prefix="/api")
app.include_router(hcg.router, prefix="/api")
app.include_router(auto_rules.router, prefix="/api")
app.include_router(voting.router, prefix="/api")
app.include_router(instructions.router, prefix="/api")
app.include_router(recipes.router, prefix="/api")
app.include_router(recipe_archive.router, prefix="/api")
app.include_router(saved_recipes.router, prefix="/api")
app.include_router(dish_notes.router, prefix="/api")
app.include_router(leftovers.router, prefix="/api")
app.include_router(expenses.router, prefix="/api")
app.include_router(health_tracking.router, prefix="/api")
app.include_router(guests.router, prefix="/api")
app.include_router(substitutions.router, prefix="/api")
app.include_router(ordering.router, prefix="/api")
app.include_router(grocery_baskets.router, prefix="/api")
app.include_router(your_kitchen.router, prefix="/api")
# Investor router carries its own /api/* prefixes (events ingestion + investor surface)
app.include_router(investor.router)
app.include_router(swiggy_auth.router)
# Pilot founder dashboard (own /api/pilot prefix)
app.include_router(pilot.router)

# Static assets: founder pilot dashboard ships from app/static.
_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")
