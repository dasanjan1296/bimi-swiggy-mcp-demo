from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import settings

# 2026-05-03: NullPool — every session opens a fresh asyncpg connection.
#
# Why: APScheduler's `BackgroundScheduler` callbacks call `asyncio.run()` to
# invoke async work, which spawns a new event loop in a worker thread. The
# default pool reuses connections across loops; once a job touches a pooled
# connection, any later request that picks up the same connection 500s with
# `cannot perform operation: another operation is in progress` (asyncpg
# refuses cross-loop access). The bug is intermittent — the user has hit it
# three times today across OTP send, Your Kitchen load, and dev-login —
# always after the scheduler has been running for a few minutes.
#
# Two fixes were on the table:
#   1. Migrate to `AsyncIOScheduler` so jobs run on the FastAPI loop. Right
#      fix, but every job function needs an async-native rewrite (~30+ min).
#   2. NullPool — disable pooling entirely. Each request gets its own
#      connection, no sharing across loops. Adds ~10-30ms per request for a
#      fresh connect. Structural fix, contained to this file.
#
# Going with (2) because the connection-overhead cost is negligible at our
# traffic and the bug class disappears completely. Revisit (1) if/when
# request volume makes pooling worth the complexity.

# Loop 14: per-statement timeout. Without this, a single slow query (bad
# ilike, missing index, lock contention) can hold a connection forever
# and chain into total pool exhaustion. 30s is generous for our analytic
# queries (KPI aggregator) and tight enough to fail fast on a runaway
# scan. Set via asyncpg's `command_timeout` (kwarg-level cap on every
# query) PLUS `statement_timeout` server-side (Postgres-enforced cancel).
_STATEMENT_TIMEOUT_MS = 30_000  # 30 seconds


def _build_connect_args() -> dict:
    """Build asyncpg connect_args.

    SQLite (used by the test harness when BIMI_TEST_DB isn't set) doesn't
    accept these kwargs, so we only emit them for Postgres.
    """
    if settings.database_url.startswith("sqlite"):
        return {}
    return {
        "command_timeout": _STATEMENT_TIMEOUT_MS / 1000.0,
        "server_settings": {
            "statement_timeout": str(_STATEMENT_TIMEOUT_MS),
            # Hard-fail any query that would lock for > 5s waiting for
            # another transaction. Lock-wait pile-ups are the most common
            # cause of cascading timeouts in production.
            "lock_timeout": "5000",
            "application_name": "bimi-backend",
        },
    }


engine = create_async_engine(
    settings.database_url,
    echo=False,
    poolclass=NullPool,
    connect_args=_build_connect_args(),
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session
