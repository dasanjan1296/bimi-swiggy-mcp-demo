"""WhatsApp webhook dedup table — replay protection.

Revision ID: 045
Revises: 044
"""

from alembic import op
import sqlalchemy as sa


revision = "045"
down_revision = "044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "whatsapp_message_dedup",
        sa.Column("message_id", sa.String(255), primary_key=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_whatsapp_dedup_received_at",
        "whatsapp_message_dedup",
        ["received_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_whatsapp_dedup_received_at",
        table_name="whatsapp_message_dedup",
    )
    op.drop_table("whatsapp_message_dedup")
