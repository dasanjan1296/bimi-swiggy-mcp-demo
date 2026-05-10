"""Add 'cooking' status to mealplanstatus enum and ready_check_count column.

Revision ID: 021
Revises: 020
Create Date: 2026-04-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "021"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE mealplanstatus ADD VALUE IF NOT EXISTS 'cooking' BEFORE 'cooked'")
    op.add_column("meal_plans", sa.Column("ready_check_count", sa.Integer(), server_default="0", nullable=False))


def downgrade() -> None:
    op.drop_column("meal_plans", "ready_check_count")
