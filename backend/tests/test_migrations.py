"""Migration / model alignment tests.

Pins three invariants:

  1. Fresh `alembic upgrade head` succeeds end-to-end.
  2. `alembic downgrade base` then `alembic upgrade head` round-trips
     successfully (catches bad downgrade scripts before they bite ops).
  3. Every model registered on `Base.metadata` has a corresponding table
     in the live schema (catches a model added without a migration).

These tests share the same `bimi_pytest` database created by conftest's
session bootstrap, but they run all their schema operations on a *separate*
test database (`bimi_pytest_migrations`) so they don't disturb the per-test
transaction isolation used by the rest of the suite.
"""

from __future__ import annotations

import asyncio
import os

# These tests stay SYNC. Alembic's env.py spawns its own asyncio loop via
# `asyncio.run(run_async_migrations())`; if the test itself is also running
# inside an asyncio loop (pytest-asyncio), we crash with
# "asyncio.run() cannot be called from a running event loop". Keeping these
# tests sync sidesteps the conflict entirely.

_MIG_DB = "bimi_pytest_migrations"
_TEST_DB_HOST = os.getenv("BIMI_TEST_DB_HOST", "localhost")
_TEST_DB_PORT = os.getenv("BIMI_TEST_DB_PORT", "5433")
_TEST_DB_USER = os.getenv("BIMI_TEST_DB_USER", "bimi")
_TEST_DB_PASS = os.getenv("BIMI_TEST_DB_PASS", "bimi")
_MIG_DB_URL = (
    f"postgresql+asyncpg://{_TEST_DB_USER}:{_TEST_DB_PASS}@"
    f"{_TEST_DB_HOST}:{_TEST_DB_PORT}/{_MIG_DB}"
)


def _recreate_mig_db_sync() -> None:
    """Synchronous DB recreate using asyncio.run — safe because these tests
    are themselves synchronous (no outer event loop)."""
    import asyncpg

    async def _do() -> None:
        admin = await asyncpg.connect(
            user=_TEST_DB_USER, password=_TEST_DB_PASS,
            host=_TEST_DB_HOST, port=int(_TEST_DB_PORT), database="postgres",
        )
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{_MIG_DB}"')
            await admin.execute(f'CREATE DATABASE "{_MIG_DB}"')
        finally:
            await admin.close()

    asyncio.run(_do())


def _alembic_cmd(direction: str, target: str = "head") -> None:
    """Run an alembic command synchronously against the migration test DB.

    NOTE: `alembic/env.py` checks `os.environ["DATABASE_URL"]` and uses it
    UNCONDITIONALLY, overriding anything we set via `cfg.set_main_option`.
    The conftest's session bootstrap pins DATABASE_URL to `bimi_pytest`, so
    we have to monkey-patch env to point at our migration test DB for the
    duration of the alembic call.
    """
    from alembic.config import Config

    from alembic import command

    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", _MIG_DB_URL)

    saved_db_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = _MIG_DB_URL
    try:
        if direction == "upgrade":
            command.upgrade(cfg, target)
        elif direction == "downgrade":
            command.downgrade(cfg, target)
        else:  # pragma: no cover
            raise ValueError(f"Unknown direction: {direction}")
    finally:
        if saved_db_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = saved_db_url


def _live_table_names() -> set[str]:
    """Reflect the migration test DB and return its table names."""
    import asyncpg

    async def _do() -> set[str]:
        conn = await asyncpg.connect(_MIG_DB_URL.replace("+asyncpg", ""))
        try:
            rows = await conn.fetch(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            )
            return {r["tablename"] for r in rows}
        finally:
            await conn.close()

    return asyncio.run(_do())


def test_fresh_upgrade_head_is_clean():
    """Upgrade from base to head on a virgin DB — must complete without raising."""
    _recreate_mig_db_sync()
    _alembic_cmd("upgrade", "head")


def test_downgrade_base_then_upgrade_head_round_trip():
    """Migrate the freshly-upgraded DB all the way down and back up. This
    catches bad `downgrade()` blocks before they bite ops in a rollback."""
    _recreate_mig_db_sync()
    _alembic_cmd("upgrade", "head")
    _alembic_cmd("downgrade", "base")
    _alembic_cmd("upgrade", "head")


def test_every_model_has_a_table():
    """Reflect the live schema and ensure every table in
    `Base.metadata.tables` actually exists. Catches the case where a
    `models/foo.py` was added but a migration to create the table was
    forgotten."""
    _recreate_mig_db_sync()
    _alembic_cmd("upgrade", "head")

    # Import all models so they register on Base.metadata.
    import app.models  # noqa: F401  side-effect: register every model
    from app.db import Base

    db_tables = _live_table_names()
    declared_tables = {t.name for t in Base.metadata.tables.values()}
    missing = declared_tables - db_tables - {"alembic_version"}

    assert not missing, (
        f"{len(missing)} model(s) declare a table that does not exist in the "
        f"live schema. Add an Alembic migration to create them. Missing: "
        f"{sorted(missing)}"
    )


def test_no_orphan_instacook_or_rides_or_uc_tables():
    """Belt-and-braces guard: after Phase 0.3 + 0.4 retirements, there must
    be ZERO instacook / rides / multi-platform tables in the schema, even
    if a future migration accidentally re-creates one.
    """
    _recreate_mig_db_sync()
    _alembic_cmd("upgrade", "head")

    db_tables = _live_table_names()

    forbidden_prefixes = ("instacook_", "ride_", "saved_loc", "pre_auth")
    forbidden_exact = {
        "memberships", "savings_events", "household_credits",
        "platform_sessions", "service_bookings",
    }

    orphans = [
        t for t in db_tables if t.startswith(forbidden_prefixes) or t in forbidden_exact
    ]
    assert not orphans, (
        f"Found {len(orphans)} retired tables in the schema — a migration "
        f"re-introduced them. Orphans: {sorted(orphans)}"
    )
