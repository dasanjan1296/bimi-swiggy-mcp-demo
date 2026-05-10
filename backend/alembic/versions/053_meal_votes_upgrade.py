"""Upgrade `meal_votes` for cross-device sync + InstaCook profiling.

Three changes:
  1. Add `is_proxy` boolean — distinguishes AI-cast votes from member
     votes. Required so the past-day modal can show the violet
     "AI voted X" attribution and so InstaCook can weight proxy votes
     differently when learning preference posteriors.
  2. Add `meal_date_d` (date) — the existing `meal_date` is a String(20)
     hard-wired to "tomorrow" in the router. Cross-device sync needs a
     real date column so vote/finalize payloads can target any future
     day. Backfill from the text column where possible, else from
     `created_at + 1 day`. We keep the old text column nullable for one
     release so an in-flight worker can still read it; a follow-up
     migration removes it.
  3. Refresh the UNIQUE constraint to use `meal_date_d` so multiple
     votes from the same member on different days don't collide.

The router code reads/writes both columns during the transition.

Revision ID: 053
Revises: 052
"""
from alembic import op
import sqlalchemy as sa


revision = "053"
down_revision = "052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. is_proxy column (default false; existing rows are member votes).
    op.add_column(
        "meal_votes",
        sa.Column(
            "is_proxy",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
    )

    # 2. New typed date column. Nullable initially so we can backfill
    #    before flipping to NOT NULL.
    op.add_column(
        "meal_votes",
        sa.Column("meal_date_d", sa.Date, nullable=True),
    )

    # Backfill: parse the existing text column when it looks like
    # yyyy-mm-dd. Anything else (e.g. literal "tomorrow") falls back to
    # date(created_at) + 1 day, which matches what the router meant by
    # "tomorrow" at write time.
    op.execute(
        """
        UPDATE meal_votes
        SET meal_date_d = CASE
            WHEN meal_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
                THEN meal_date::date
            ELSE (created_at AT TIME ZONE 'UTC')::date + 1
        END
        WHERE meal_date_d IS NULL
        """
    )

    # Flip to NOT NULL once backfilled.
    op.alter_column("meal_votes", "meal_date_d", nullable=False)

    # 3. Replace the UNIQUE constraint to key off the typed date.
    # We drop both the constraint and the underlying index defensively.
    # Some databases came through 046 with partial state — the
    # constraint metadata was cleared but the backing index wasn't,
    # which causes ADD CONSTRAINT to fail on "relation already exists".
    op.execute(
        "ALTER TABLE meal_votes DROP CONSTRAINT IF EXISTS uq_meal_votes_idempotency"
    )
    op.execute(
        "DROP INDEX IF EXISTS uq_meal_votes_idempotency"
    )
    op.create_unique_constraint(
        "uq_meal_votes_idempotency",
        "meal_votes",
        ["family_id", "member_id", "meal_date_d", "meal_type", "dish_name"],
    )

    # Helpful covering index for the meal-history query (read-heavy
    # path: WHERE family_id = ? AND meal_date_d BETWEEN ? AND ?).
    op.create_index(
        "ix_meal_votes_family_date_d",
        "meal_votes",
        ["family_id", "meal_date_d"],
    )


def downgrade() -> None:
    op.drop_index("ix_meal_votes_family_date_d", table_name="meal_votes")
    op.drop_constraint(
        "uq_meal_votes_idempotency",
        "meal_votes",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_meal_votes_idempotency",
        "meal_votes",
        ["family_id", "member_id", "meal_date", "meal_type", "dish_name"],
    )
    op.drop_column("meal_votes", "meal_date_d")
    op.drop_column("meal_votes", "is_proxy")
