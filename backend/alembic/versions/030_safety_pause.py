"""A3: families.suggestions_paused_at + reason for pilot safety-pause.

If a pilot family reports an issue (allergic reaction, dietary violation,
LLM misbehaviour) the founder can pause meal suggestions for that family
without taking the whole pilot down. The meal_engine consults this column
and short-circuits to a "paused, please contact founder" response.

Revision ID: 030
Revises: 029
"""

from alembic import op
import sqlalchemy as sa

revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "families",
        sa.Column("suggestions_paused_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "families",
        sa.Column("suggestions_paused_reason", sa.String(255), nullable=True),
    )
    op.create_index(
        "ix_families_suggestions_paused_at",
        "families",
        ["suggestions_paused_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_families_suggestions_paused_at", table_name="families")
    op.drop_column("families", "suggestions_paused_reason")
    op.drop_column("families", "suggestions_paused_at")
