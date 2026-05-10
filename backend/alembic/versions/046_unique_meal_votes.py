"""Loop 9: UNIQUE constraint on meal_votes idempotency tuple.

Prevents the read-then-write race in `routers/voting.py::cast_vote` where
two parallel votes from the same member for the same dish could both
pass the pre-check SELECT and both INSERT — producing duplicate rows
that break Nash fairness scoring.

Revision ID: 046
Revises: 045
"""

from alembic import op


revision = "046"
down_revision = "045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # First, dedup any existing duplicates so the constraint can be applied.
    # Keep the OLDEST row (smallest created_at).
    op.execute(
        """
        DELETE FROM meal_votes mv
        USING meal_votes dup
        WHERE mv.family_id = dup.family_id
          AND mv.member_id = dup.member_id
          AND mv.meal_date = dup.meal_date
          AND mv.meal_type = dup.meal_type
          AND mv.dish_name = dup.dish_name
          AND mv.created_at > dup.created_at
        """
    )
    op.create_unique_constraint(
        "uq_meal_votes_idempotency",
        "meal_votes",
        ["family_id", "member_id", "meal_date", "meal_type", "dish_name"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_meal_votes_idempotency",
        "meal_votes",
        type_="unique",
    )
