"""Create auto_approval_rules table.

The `AutoApprovalRule` model has existed since the original household-mode
rollout but never had its own Alembic migration — the seed scripts created
the table via `Base.metadata.create_all`. This migration backfills the
schema so the model<->migration drift test passes and so any deployment
without a seed step still gets the table.

Revision ID: 043
Revises: 042
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "043"
down_revision = "042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auto_approval_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "family_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("families.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("max_amount", sa.Float, nullable=False, server_default="500.0"),
        sa.Column("min_days_since_last_order", sa.Integer, nullable=False, server_default="5"),
        sa.Column("trusted_items", postgresql.ARRAY(sa.String), nullable=True),
        sa.Column("time_window_start", sa.String(10), nullable=True),
        sa.Column("time_window_end", sa.String(10), nullable=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", sa.String(255), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_auto_approval_rules_family_enabled",
        "auto_approval_rules",
        ["family_id", "enabled"],
    )


def downgrade() -> None:
    op.drop_index("ix_auto_approval_rules_family_enabled", table_name="auto_approval_rules")
    op.drop_table("auto_approval_rules")
