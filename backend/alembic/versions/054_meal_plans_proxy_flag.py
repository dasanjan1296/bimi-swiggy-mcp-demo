"""Add `finalized_by_proxy` boolean to `meal_plans`.

When the AI-proxy task closes a vote (today: a skeleton; tomorrow:
Thompson sampling over member preference posteriors), the resulting
plan row should be flagged so the past-day modal and downstream
analytics can distinguish "the household chose this" from "Bimi chose
this on the household's behalf because nobody voted in time."

Revision ID: 054
Revises: 053
"""
from alembic import op
import sqlalchemy as sa


revision = "054"
down_revision = "053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "meal_plans",
        sa.Column(
            "finalized_by_proxy",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("meal_plans", "finalized_by_proxy")
