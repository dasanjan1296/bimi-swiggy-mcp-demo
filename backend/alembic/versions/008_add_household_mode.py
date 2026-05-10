"""Add household mode: inventory, meal logs, absences, parent role fields

Revision ID: 008
Revises: 007
Create Date: 2026-04-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "household_inventory",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("item_name", sa.String(255), nullable=False),
        sa.Column("brand", sa.String(255), nullable=True),
        sa.Column("quantity_remaining", sa.Float, nullable=False, server_default="0"),
        sa.Column("unit", sa.String(50), nullable=False, server_default="units"),
        sa.Column("last_restocked", sa.DateTime(timezone=True), nullable=True),
        sa.Column("estimated_depletion_rate", sa.Float, nullable=True),
        sa.Column("is_staple", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("category", sa.String(50), nullable=False, server_default="other"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "meal_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("meal_type", sa.String(20), nullable=False),
        sa.Column("dishes", postgresql.ARRAY(sa.String), nullable=True),
        sa.Column("cooked_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("parents.id"), nullable=True),
        sa.Column("source", sa.String(20), nullable=False, server_default="home_cook"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "househelp_absences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("parents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("replacement_booked", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("replacement_platform", sa.String(100), nullable=True),
        sa.Column("replacement_deep_link", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.add_column("parents", sa.Column("role", sa.String(50), nullable=False, server_default="parent"))
    op.add_column("parents", sa.Column("role_schedule", sa.String(200), nullable=True))
    op.add_column("parents", sa.Column("monthly_salary", sa.Float, nullable=True))


def downgrade() -> None:
    op.drop_column("parents", "monthly_salary")
    op.drop_column("parents", "role_schedule")
    op.drop_column("parents", "role")
    op.drop_table("househelp_absences")
    op.drop_table("meal_logs")
    op.drop_table("household_inventory")
