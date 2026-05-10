"""Async test harness for Bimi backend.

What this fixture stack provides:

  - `event_loop`              : session-scoped asyncio loop (pytest-asyncio default)
  - `_test_db_url`            : URL for the per-process test Postgres database
  - `_engine` (session)       : single AsyncEngine pointing at the test DB,
                                schema migrated once per session
  - `db` (function)            : a fresh AsyncSession wrapped in a SAVEPOINT
                                that ROLLBACKs at end of test — every test
                                sees a clean DB even with shared inserts
  - `client` (function)       : `httpx.AsyncClient` over `ASGITransport(app)`
                                — no live uvicorn needed
  - `seed_family` (function)  : pre-seeds a family + child + a few inventory
                                items, returns the seeded ids/credentials
  - `auth_headers` (function) : returns `{"Authorization": "Bearer <jwt>"}`
                                for the seeded child

DB strategy: a separate Postgres database `bimi_pytest` is created at session
start, all migrations are applied once, then each test runs in a transaction
that gets rolled back. The test DB is dropped + recreated between sessions.

The test session forces several env safeguards before importing the app:
  - `BIMI_DISABLE_SCHEDULER=1` — APScheduler doesn't start in the lifespan
  - `DATABASE_URL`             — points at the test DB
  - `BIMI_ENV=test`            — locks down dev affordances
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
# Pre-import env setup. MUST happen before any `from app...` import.
# ---------------------------------------------------------------------------

_TEST_DB_NAME = os.getenv("BIMI_TEST_DB_NAME", "bimi_pytest")
_TEST_DB_HOST = os.getenv("BIMI_TEST_DB_HOST", "localhost")
_TEST_DB_PORT = os.getenv("BIMI_TEST_DB_PORT", "5433")
_TEST_DB_USER = os.getenv("BIMI_TEST_DB_USER", "bimi")
_TEST_DB_PASS = os.getenv("BIMI_TEST_DB_PASS", "bimi")

_TEST_DB_URL = (
    f"postgresql+asyncpg://{_TEST_DB_USER}:{_TEST_DB_PASS}@"
    f"{_TEST_DB_HOST}:{_TEST_DB_PORT}/{_TEST_DB_NAME}"
)
_TEST_DB_URL_SYNC = (
    f"postgresql://{_TEST_DB_USER}:{_TEST_DB_PASS}@"
    f"{_TEST_DB_HOST}:{_TEST_DB_PORT}/postgres"
)

os.environ["DATABASE_URL"] = _TEST_DB_URL
os.environ.setdefault("BIMI_ENV", "test")
os.environ.setdefault("BIMI_DISABLE_SCHEDULER", "1")
os.environ.setdefault("SECRET_KEY", "test-secret-do-not-use-in-prod-" + "x" * 32)


# ---------------------------------------------------------------------------
# Database lifecycle
# ---------------------------------------------------------------------------


def _ensure_test_db_exists() -> None:
    """Create the per-session test database if it doesn't exist.

    Uses synchronous psycopg/asyncpg-blocking connection because alembic + DB
    creation happens before any async loop starts.
    """
    import asyncpg

    async def _ensure() -> None:
        # Connect to the default `postgres` database so we can CREATE/DROP the
        # test DB. We DROP first to guarantee a clean schema each session — the
        # in-transaction rollback handles per-test isolation, but stale schema
        # from a previously-failed run would still bite.
        admin = await asyncpg.connect(
            user=_TEST_DB_USER, password=_TEST_DB_PASS,
            host=_TEST_DB_HOST, port=int(_TEST_DB_PORT), database="postgres",
        )
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{_TEST_DB_NAME}"')
            await admin.execute(f'CREATE DATABASE "{_TEST_DB_NAME}"')
        finally:
            await admin.close()

    asyncio.run(_ensure())


def _run_alembic_upgrade_head() -> None:
    """Apply all migrations to the test DB. Runs synchronously."""
    from alembic.config import Config

    from alembic import command

    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", _TEST_DB_URL)
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session", autouse=True)
def _bootstrap_test_db() -> None:
    """Once per session: drop+create the test DB, apply migrations."""
    _ensure_test_db_exists()
    _run_alembic_upgrade_head()


# ---------------------------------------------------------------------------
# Engine + session fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def _engine():
    """Per-test AsyncEngine. Schema is created once by the session-scoped
    `_bootstrap_test_db` fixture; the engine here only opens connections.

    We deliberately use a function-scoped engine (rather than session-scoped)
    because pytest-asyncio 1.x runs each test in its own event loop, and an
    asyncpg connection from a different loop raises "Task got Future
    attached to a different loop". A fresh engine per test sidesteps that
    entirely; engine creation is cheap (~5ms) once Postgres is warm.
    """
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(_TEST_DB_URL, poolclass=NullPool, future=True)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db(_engine) -> AsyncIterator:
    """Per-test AsyncSession on a SAVEPOINT that rolls back at end-of-test.

    Uses SQLAlchemy 2.0's `join_transaction_mode="create_savepoint"`: the
    session opens a SAVEPOINT inside the connection's outer transaction.
    Any `session.commit()` inside the SUT just commits the savepoint, not
    the outer transaction — so when we roll back the outer transaction at
    end-of-test, the DB is restored to its pre-test state.

    See https://docs.sqlalchemy.org/en/20/orm/session_transaction.html
        #joining-a-session-into-an-external-transaction-such-as-for-test-suites
    """
    from sqlalchemy.ext.asyncio import AsyncSession

    async with _engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield session
        finally:
            await session.close()
            if transaction.is_active:
                await transaction.rollback()


# ---------------------------------------------------------------------------
# Application client (in-process ASGI — no live uvicorn)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client(db) -> AsyncIterator:
    """An `httpx.AsyncClient` that talks to the FastAPI app in-process via
    ASGITransport, with `get_db` overridden to yield the test session."""
    import httpx

    from app.db import get_db
    from app.main import app

    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test",
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def seed_family(db) -> dict:
    """Insert a deterministic family + child + a few inventory items.

    Returns:
        {
          "family_id": UUID,
          "child_id":  UUID,
          "phone":     "+919900000002",
          "password":  "demo1234",
        }
    """
    from app.models.family import Child, Family
    from app.models.inventory import InventoryItem
    from app.services.auth import hash_password

    family_id = uuid.UUID("00000000-0000-0000-0000-000000000099")
    family = Family(
        id=family_id,
        name="Test Family",
        family_type="household",
        auto_approve_threshold=200,
    )
    db.add(family)

    child = Child(
        family_id=family_id,
        name="Test Child",
        phone="+919900000099",
        password_hash=hash_password("demo1234"),
    )
    db.add(child)
    await db.flush()  # make child.id available

    db.add_all([
        InventoryItem(
            family_id=family_id, item_name="Atta", brand="Aashirvaad",
            quantity_remaining=4.0, unit="kg", is_staple=True, category="grains",
        ),
        InventoryItem(
            family_id=family_id, item_name="Basmati Rice", brand="India Gate",
            quantity_remaining=3.0, unit="kg", is_staple=True, category="grains",
        ),
        InventoryItem(
            family_id=family_id, item_name="Milk", brand="Nandini",
            quantity_remaining=1.0, unit="litre", is_staple=True, category="dairy",
        ),
    ])
    await db.flush()

    return {
        "family_id": family_id,
        "child_id": child.id,
        "phone": "+919900000099",
        "password": "demo1234",
    }


@pytest_asyncio.fixture
async def auth_headers(seed_family) -> dict:
    """Return Authorization headers for the seeded child as `{"Authorization": "Bearer ..."}`."""
    from app.services.auth import create_access_token

    token = create_access_token({
        "sub": str(seed_family["child_id"]),
        "family_id": str(seed_family["family_id"]),
    })
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Adapter fixtures — every test runs against deterministic Fake adapters
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def fake_adapters():
    """Auto-install Fake adapters for every test, regardless of `settings`.

    Tests that need to assert against the recorded calls can request the
    individual fixtures (`fake_llm`, `fake_whatsapp`, `fake_transcription`,
    `fake_mcp_swiggy`) which return the same instances installed here.

    Yields a dict of all five fakes for tests that want everything in one
    handle.
    """
    from app.adapters import (
        FakeLLMAdapter,
        FakeOtpSender,
        FakeSwiggyMCPAdapter,
        FakeTranscriptionAdapter,
        FakeWhatsAppAdapter,
        reset_all_adapter_caches,
        set_llm_adapter,
        set_mcp_swiggy_adapter,
        set_otp_sender,
        set_transcription_adapter,
        set_whatsapp_adapter,
    )

    fakes = {
        "llm": FakeLLMAdapter(),
        "whatsapp": FakeWhatsAppAdapter(),
        "transcription": FakeTranscriptionAdapter(),
        "mcp_swiggy": FakeSwiggyMCPAdapter(),
        "otp": FakeOtpSender(),
    }

    set_llm_adapter(fakes["llm"])
    set_whatsapp_adapter(fakes["whatsapp"])
    set_transcription_adapter(fakes["transcription"])
    set_mcp_swiggy_adapter(fakes["mcp_swiggy"])
    set_otp_sender(fakes["otp"])

    try:
        yield fakes
    finally:
        reset_all_adapter_caches()


@pytest.fixture
def fake_llm(fake_adapters):
    return fake_adapters["llm"]


@pytest.fixture
def fake_whatsapp(fake_adapters):
    return fake_adapters["whatsapp"]


@pytest.fixture
def fake_transcription(fake_adapters):
    return fake_adapters["transcription"]


@pytest.fixture
def fake_mcp_swiggy(fake_adapters):
    return fake_adapters["mcp_swiggy"]


@pytest.fixture
def fake_otp(fake_adapters):
    return fake_adapters["otp"]
