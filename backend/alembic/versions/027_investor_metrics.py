"""Investor metrics infrastructure: cohort flag + events + kpi_snapshots + investor_sessions.

Adds the data foundation for the venture-grade dashboard:

  1. families.cohort  - lets us segment "pilot_v1" vs production families.
  2. events            - raw, append-only product event stream (mobile + backend).
  3. kpi_snapshots     - precomputed KPI values written every 60s by the
                          aggregator scheduler. The dashboard reads from here
                          so panels render in <100ms regardless of event volume.
  4. investor_sessions - meta-analytics on which VC opened the dashboard,
                          when, and which panels they actually scrolled to.

Revision ID: 027
Revises: 026
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Cohort flag on families
    op.add_column(
        "families",
        sa.Column("cohort", sa.String(50), nullable=True),
    )
    op.create_index("ix_families_cohort", "families", ["cohort"])

    # 2. Raw event stream
    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "family_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("families.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("cohort", sa.String(50), nullable=True),
        # Who/what triggered the event: child | parent | cook | system | bimi
        sa.Column("actor_type", sa.String(20), nullable=False, server_default="system"),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        # Domain event name in snake_case, e.g. "instacook_booking_completed"
        sa.Column("event_type", sa.String(80), nullable=False),
        # Free-form structured payload. PII-stripped before insert by analytics.track().
        sa.Column("properties", postgresql.JSONB, nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("source", sa.String(20), nullable=False, server_default="backend"),
    )
    # Indices target the two access patterns the aggregator hits:
    #   (a) "give me all events of type X in window" -> event_type + occurred_at
    #   (b) "give me one family's timeline" -> family_id + occurred_at
    op.create_index("ix_events_type_occurred", "events", ["event_type", "occurred_at"])
    op.create_index("ix_events_family_occurred", "events", ["family_id", "occurred_at"])
    op.create_index("ix_events_cohort_occurred", "events", ["cohort", "occurred_at"])

    # 3. Precomputed KPI snapshots
    op.create_table(
        "kpi_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "snapshot_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("kpi_name", sa.String(80), nullable=False),
        # Scope: global | cohort | family
        sa.Column("scope", sa.String(20), nullable=False, server_default="global"),
        sa.Column("scope_id", sa.String(80), nullable=True),
        # Single primary number (NaN/null OK for "no data yet" case)
        sa.Column("value", sa.Float, nullable=True),
        # Full payload for charts (cohort tables, histograms, etc.)
        sa.Column("payload", postgresql.JSONB, nullable=True),
    )
    op.create_index(
        "ix_kpi_snapshots_lookup",
        "kpi_snapshots",
        ["kpi_name", "scope", "scope_id", "snapshot_at"],
    )

    # 4. Investor session tracking (so we know which VC scrolled to which panel)
    op.create_table(
        "investor_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        # JWT id (jti claim) - lookup hot path
        sa.Column("jwt_jti", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("panels_viewed", postgresql.JSONB, nullable=True),
        sa.Column("ip", sa.String(45), nullable=True),
        # Founder-mode flag: lets us flip on real names + per-family timelines
        sa.Column("is_founder", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_investor_sessions_email", "investor_sessions", ["email"])


def downgrade() -> None:
    op.drop_index("ix_investor_sessions_email", table_name="investor_sessions")
    op.drop_table("investor_sessions")

    op.drop_index("ix_kpi_snapshots_lookup", table_name="kpi_snapshots")
    op.drop_table("kpi_snapshots")

    op.drop_index("ix_events_cohort_occurred", table_name="events")
    op.drop_index("ix_events_family_occurred", table_name="events")
    op.drop_index("ix_events_type_occurred", table_name="events")
    op.drop_table("events")

    op.drop_index("ix_families_cohort", table_name="families")
    op.drop_column("families", "cohort")
