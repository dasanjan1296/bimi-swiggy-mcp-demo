"""Add `dish_notes` table for household-shared cook instructions
captured when rating past meals.

Schema notes:
  • `author_name` is denormalised text (not a FK). The household has
    `parents` + `children` split tables and no unified members PK,
    so a polymorphic FK is overhead we don't need for a byline.
  • `source_date` is a yyyy-mm-dd text column, matching the rest of
    the schema's date columns.
  • Two composite indexes serve the two hot paths:
      - cook-brief composer: WHERE family_id = ? AND dish_name = ?
        AND is_active ORDER BY created_at DESC LIMIT 3
      - past-day modal: WHERE family_id = ? AND source_date = ?
        AND is_active

Revision ID: 052
Revises: 051
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "052"
down_revision = "051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dish_notes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        # Ownership / scope
        sa.Column(
            "family_id",
            UUID(as_uuid=True),
            sa.ForeignKey("families.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("author_name", sa.String(120), nullable=False),
        # Subject
        sa.Column("dish_name", sa.String(255), nullable=False),
        sa.Column("meal_type", sa.String(20), nullable=True),
        sa.Column("source_date", sa.String(10), nullable=False),
        # Content
        sa.Column("note_text", sa.Text, nullable=False),
        # Lifecycle
        sa.Column(
            "is_active",
            sa.Boolean,
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    op.create_index(
        "ix_dish_notes_family_dish_active",
        "dish_notes",
        ["family_id", "dish_name", "is_active"],
    )
    op.create_index(
        "ix_dish_notes_family_date_active",
        "dish_notes",
        ["family_id", "source_date", "is_active"],
    )


def downgrade() -> None:
    op.drop_index("ix_dish_notes_family_date_active", table_name="dish_notes")
    op.drop_index("ix_dish_notes_family_dish_active", table_name="dish_notes")
    op.drop_table("dish_notes")
