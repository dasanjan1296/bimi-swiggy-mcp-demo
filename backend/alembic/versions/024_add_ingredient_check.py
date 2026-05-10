"""Add ingredient_checks table for cook ingredient verification via WhatsApp.

Revision ID: 024
Revises: 023
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ingredient_checks",
        sa.Column("id", UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("family_id", UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), nullable=False),
        sa.Column("meal_name", sa.String(200), nullable=False),
        sa.Column("meal_type", sa.String(20), nullable=False),
        sa.Column("meal_date", sa.String(10), nullable=False),
        sa.Column("cook_phone", sa.String(20), nullable=False),
        sa.Column("all_ingredients_json", sa.Text, server_default="[]"),
        sa.Column("missing_items_json", sa.Text, server_default="[]"),
        sa.Column("state", sa.String(30), server_default="pending"),
        sa.Column("sent_message_id", sa.String(100), nullable=True),
        sa.Column("reminder_sent", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ingredient_checks_family_state", "ingredient_checks", ["family_id", "state"])


def downgrade() -> None:
    op.drop_index("ix_ingredient_checks_family_state")
    op.drop_table("ingredient_checks")
