"""ORM for the investor metrics infrastructure.

Three tables (added by alembic 027):

  - Event           : raw, append-only product event stream. Written by
                       services/analytics.py from both backend and mobile.
  - KpiSnapshot     : precomputed KPI values written every 60s by the
                       kpi_aggregator scheduler.
  - InvestorSession : magic-link login records + per-VC panel-view tracking.

These are deliberately lightweight: nothing here writes to other tables,
nothing here has back-references. The aggregator queries them directly.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ActorType(str, enum.Enum):
    CHILD = "child"
    PARENT = "parent"
    COOK = "cook"
    SYSTEM = "system"
    BIMI = "bimi"


class EventSource(str, enum.Enum):
    BACKEND = "backend"
    MOBILE = "mobile"
    WEB = "web"


class KpiScope(str, enum.Enum):
    GLOBAL = "global"
    COHORT = "cohort"
    FAMILY = "family"


class Event(Base):
    """One row per meaningful product event. Append-only, never updated.

    PII is stripped from `properties` before insert (see analytics._scrub_pii).
    Phone numbers, full names, and health conditions never live here.
    """
    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    family_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=True,
    )
    cohort: Mapped[str | None] = mapped_column(String(50), nullable=True)

    actor_type: Mapped[str] = mapped_column(String(20), nullable=False, default=ActorType.SYSTEM.value)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    properties: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    source: Mapped[str] = mapped_column(String(20), nullable=False, default=EventSource.BACKEND.value)


class KpiSnapshot(Base):
    """One row per KPI per scope per refresh tick.

    The aggregator writes a fresh row every 60s; the dashboard reads only
    the most recent row per (kpi_name, scope, scope_id). Older rows are
    retained for trend charts (sparklines).
    """
    __tablename__ = "kpi_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    kpi_name: Mapped[str] = mapped_column(String(80), nullable=False)
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default=KpiScope.GLOBAL.value)
    scope_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # Single primary number; null when payload-only (e.g. histograms)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Full payload for charts: cohort grids, histograms, narrative strings, etc.
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class InvestorSession(Base):
    """Magic-link auth + meta-analytics for fundraising.

    `panels_viewed` is a JSON dict of {panel_id: {first_seen, last_seen, view_count}}
    so the founder can see which sections each VC actually scrolled to. That's
    a powerful signal for follow-up sequencing.
    """
    __tablename__ = "investor_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    jwt_jti: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    panels_viewed: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)

    # Founder-mode unlocks per-family timelines + real names. Set true only
    # for the founder's own JWT, never for outside investors.
    is_founder: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
