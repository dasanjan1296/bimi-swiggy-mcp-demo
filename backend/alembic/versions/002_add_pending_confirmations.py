"""Add pending_confirmations table

Revision ID: 002
Revises: 001
Create Date: 2026-04-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    confirmation_state = postgresql.ENUM(
        "awaiting_confirmation",
        "awaiting_disambiguation",
        "awaiting_clarification",
        "awaiting_item_correction",
        "resolved",
        "expired",
        name="confirmationstate",
        create_type=True,
    )

    op.create_table(
        "pending_confirmations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("parents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), nullable=False),
        sa.Column("state", confirmation_state, server_default="awaiting_confirmation"),
        sa.Column("extracted_items_json", sa.Text, server_default="[]"),
        sa.Column("source_type", sa.String(20), server_default="voice"),
        sa.Column("raw_transcript", sa.Text, nullable=True),
        sa.Column("overall_confidence", sa.Float, server_default="0.0"),
        sa.Column("correction_item_index", sa.Integer, nullable=True),
        sa.Column("sent_message_id", sa.String(100), nullable=True),
        sa.Column("attempt_count", sa.Integer, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index("ix_pending_confirmations_parent_state", "pending_confirmations", ["parent_id", "state"])


def downgrade() -> None:
    op.drop_index("ix_pending_confirmations_parent_state")
    op.drop_table("pending_confirmations")
    op.execute("DROP TYPE IF EXISTS confirmationstate")
