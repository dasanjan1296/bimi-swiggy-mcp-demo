"""Add meal_plans table for pre-planning feature.

Revision ID: 011
Revises: 010
Create Date: 2026-04-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, ARRAY

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "meal_plans",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("family_id", UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("date", sa.Date(), nullable=False, index=True),
        sa.Column("meal_type", sa.String(20), nullable=False),
        sa.Column("selected_meal", sa.String(255), nullable=False),
        sa.Column("dishes", ARRAY(sa.String), server_default="{}"),
        sa.Column("missing_ingredients_json", sa.Text(), nullable=True),
        sa.Column("fallback_meal", sa.String(255), nullable=True),
        sa.Column("fallback_dishes", ARRAY(sa.String), nullable=True),
        sa.Column("cook_arrival_time", sa.Time(), nullable=True),
        sa.Column("auto_order", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("cart_id", UUID(as_uuid=True), sa.ForeignKey("carts.id"), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "planned", "ingredients_ordered", "ingredients_delivered",
                "fallback_activated", "cooked", "cancelled",
                name="mealplanstatus",
            ),
            server_default="planned",
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("meal_plans")
    op.execute("DROP TYPE IF EXISTS mealplanstatus")
