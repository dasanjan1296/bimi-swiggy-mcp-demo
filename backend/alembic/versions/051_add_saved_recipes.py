"""Add `saved_recipes` table for the household-curated YouTube /
Instagram recipe catalog surfaced in the home "Self cook ideas" sheet.

Lighter shape than `recipes` (no ingredients / nutrition / GPT context):
we only need a title, link, image, and minimal classification to
render a card and route the user back to the source.

Revision ID: 051
Revises: 050
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, UUID


revision = "051"
down_revision = "050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "saved_recipes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        # Ownership
        sa.Column(
            "family_id",
            UUID(as_uuid=True),
            sa.ForeignKey("families.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_by_name", sa.String(120), nullable=True),
        # Source
        sa.Column("source_url", sa.Text, nullable=False),
        sa.Column("source_platform", sa.String(20), nullable=False),
        # Display
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("image_url", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        # Classification
        sa.Column(
            "course",
            sa.String(20),
            nullable=False,
            server_default="any",
        ),
        sa.Column("total_time_mins", sa.Integer, nullable=True),
        sa.Column("tags", ARRAY(sa.String), nullable=True),
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

    # Plain index on family_id (catch-all for ad-hoc joins / lookups).
    op.create_index(
        "ix_saved_recipes_family_id",
        "saved_recipes",
        ["family_id"],
    )

    # Hot path composite — list active saved recipes for a family,
    # optionally filtered to a single course.
    op.create_index(
        "ix_saved_recipes_family_active_course",
        "saved_recipes",
        ["family_id", "is_active", "course"],
    )

    # GIN on tags for "find saved recipes tagged X" queries.
    op.create_index(
        "ix_saved_recipes_tags",
        "saved_recipes",
        ["tags"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_saved_recipes_tags", table_name="saved_recipes")
    op.drop_index(
        "ix_saved_recipes_family_active_course",
        table_name="saved_recipes",
    )
    op.drop_index("ix_saved_recipes_family_id", table_name="saved_recipes")
    op.drop_table("saved_recipes")
