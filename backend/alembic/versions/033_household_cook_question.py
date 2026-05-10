"""Household cook question + onboarding timestamp.

Adds two columns to `families` that power the ICP-branched UX in the rework:

  has_regular_cook : Boolean, nullable
      null  -> household hasn't answered yet (unanswered bucket in the home UX)
      true  -> household has a regular cook (Malti Didi) — cook-coordination home
      false -> household has no regular cook — dish-first home
  onboarding_completed_at : Timestamp with timezone, nullable
      Set when the 3-step onboarding wraps up. Used to distinguish fresh-
      signup users from legacy ones for the one-time cook prompt.

Null default is intentional for `has_regular_cook` — we want existing users
to be prompted once on Home rather than silently bucketed as "no cook",
which would disrupt their current coordination-heavy experience.

Revision ID: 033
Revises: 032
"""

from alembic import op
import sqlalchemy as sa

revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "families",
        sa.Column("has_regular_cook", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "families",
        sa.Column(
            "onboarding_completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("families", "onboarding_completed_at")
    op.drop_column("families", "has_regular_cook")
