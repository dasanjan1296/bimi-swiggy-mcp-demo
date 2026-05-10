"""Add shared_cooks and shared_cook_households tables; relax Parent unique constraints.

Revision ID: 022
Revises: 021
Create Date: 2026-04-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shared_cooks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("phone", sa.String(20), unique=True, index=True, nullable=False),
        sa.Column("whatsapp_id", sa.String(50), unique=True, index=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("language", sa.String(20), server_default="hi", nullable=False),
        sa.Column("active_family_id", UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="SET NULL"), nullable=True),
        sa.Column("last_switched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "shared_cook_households",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("cook_id", UUID(as_uuid=True), sa.ForeignKey("shared_cooks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("family_id", UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), nullable=False),
        sa.Column("household_label", sa.String(255), nullable=False),
        sa.Column("schedule_slots", JSONB, nullable=True),
        sa.Column("monthly_salary", sa.Float, nullable=True),
        sa.Column("is_active", sa.Boolean, server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.drop_constraint("parents_phone_key", "parents", type_="unique")
    op.drop_constraint("parents_whatsapp_id_key", "parents", type_="unique")
    op.create_index("ix_parents_phone", "parents", ["phone"])
    op.create_index("ix_parents_whatsapp_id", "parents", ["whatsapp_id"])


def downgrade() -> None:
    op.drop_index("ix_parents_whatsapp_id", "parents")
    op.drop_index("ix_parents_phone", "parents")
    op.create_unique_constraint("parents_whatsapp_id_key", "parents", ["whatsapp_id"])
    op.create_unique_constraint("parents_phone_key", "parents", ["phone"])
    op.drop_table("shared_cook_households")
    op.drop_table("shared_cooks")
