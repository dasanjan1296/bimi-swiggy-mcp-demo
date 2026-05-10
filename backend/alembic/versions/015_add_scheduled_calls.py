"""Add scheduled_calls table for parent-child call coordination.

Revision ID: 015
Revises: 014
"""
from alembic import op
import sqlalchemy as sa

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scheduled_calls",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("family_id", sa.UUID(), sa.ForeignKey("families.id"), nullable=False),
        sa.Column("requester_id", sa.UUID(), sa.ForeignKey("parents.id"), nullable=False),
        sa.Column("target_child_id", sa.UUID(), sa.ForeignKey("children.id"), nullable=True),
        sa.Column("requester_name", sa.String(100), nullable=False),
        sa.Column("target_name", sa.String(100), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("timeframe_hours", sa.Integer(), nullable=False, server_default="48"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="requested"),
        sa.Column("reminder_sent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scheduled_calls_family_id", "scheduled_calls", ["family_id"])


def downgrade() -> None:
    op.drop_index("ix_scheduled_calls_family_id")
    op.drop_table("scheduled_calls")
