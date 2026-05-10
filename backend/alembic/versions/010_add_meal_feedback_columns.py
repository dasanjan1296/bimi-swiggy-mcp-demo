"""Add rating, feedback, feedback_at, nudge_sent columns to meal_logs.

Revision ID: 010
Revises: 009
Create Date: 2026-04-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "010"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("meal_logs", sa.Column("rating", sa.Integer(), nullable=True))
    op.add_column("meal_logs", sa.Column("feedback", sa.Text(), nullable=True))
    op.add_column(
        "meal_logs",
        sa.Column("feedback_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "meal_logs",
        sa.Column("nudge_sent", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("meal_logs", "nudge_sent")
    op.drop_column("meal_logs", "feedback_at")
    op.drop_column("meal_logs", "feedback")
    op.drop_column("meal_logs", "rating")
