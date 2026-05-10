"""Add recipes table for global meal archive.

Revision ID: 023
Revises: 022
Create Date: 2026-04-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision: str = "023"
down_revision: Union[str, None] = "022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "recipes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        # Identity
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("name_hindi", sa.String(255), nullable=True),
        sa.Column("slug", sa.String(255), nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
        # Classification
        sa.Column("cuisine", sa.String(50), nullable=False),
        sa.Column("course", sa.String(30), nullable=False),
        sa.Column("diet_type", sa.String(30), nullable=False),
        # Timing
        sa.Column("prep_time_mins", sa.Integer, nullable=False),
        sa.Column("cook_time_mins", sa.Integer, nullable=False),
        sa.Column("total_time_mins", sa.Integer, nullable=False),
        # Servings
        sa.Column("default_servings", sa.Integer, nullable=False, server_default="4"),
        # Layer 1: Structured JSONB
        sa.Column("ingredients", JSONB, nullable=False, server_default="[]"),
        sa.Column("instructions", JSONB, nullable=True),
        sa.Column("nutrition_per_serving", JSONB, nullable=True),
        sa.Column("health_tags", JSONB, nullable=True),
        # Layer 2: GPT-ready fields
        sa.Column("gpt_context", sa.Text, nullable=False, server_default=""),
        sa.Column("ingredient_names", ARRAY(sa.String), nullable=False, server_default="{}"),
        # Metadata
        sa.Column("difficulty", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("tags", ARRAY(sa.String), nullable=True),
        sa.Column("source_url", sa.Text, nullable=True),
        sa.Column("source_name", sa.String(255), nullable=True),
        sa.Column("youtube_search_query", sa.String(500), nullable=True),
        sa.Column("image_url", sa.Text, nullable=True),
        # Advance prep & pairing
        sa.Column("advance_prep_note", sa.Text, nullable=True),
        sa.Column("pairs_well_with", ARRAY(sa.String), nullable=True),
        # Flags
        sa.Column("is_verified", sa.Boolean, server_default="true", nullable=False),
        sa.Column("is_active", sa.Boolean, server_default="true", nullable=False),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # B-tree indexes for common filter columns
    op.create_index("ix_recipes_slug", "recipes", ["slug"])
    op.create_index("ix_recipes_cuisine", "recipes", ["cuisine"])
    op.create_index("ix_recipes_course", "recipes", ["course"])
    op.create_index("ix_recipes_diet_type", "recipes", ["diet_type"])

    # GIN indexes for array overlap and JSONB containment queries
    op.create_index("ix_recipes_ingredient_names", "recipes", ["ingredient_names"], postgresql_using="gin")
    op.create_index("ix_recipes_tags", "recipes", ["tags"], postgresql_using="gin")
    op.create_index("ix_recipes_ingredients_jsonb", "recipes", ["ingredients"], postgresql_using="gin")

    # Full-text search index on name + description
    # NOTE: array_to_string() is not IMMUTABLE in PG16+, so ingredient_names
    # is searched via its dedicated GIN array index (ix_recipes_ingredient_names) instead.
    op.execute("""
        CREATE INDEX ix_recipes_fulltext ON recipes
        USING gin (to_tsvector('english'::regconfig, coalesce(name, '') || ' ' || coalesce(description, '')))
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_recipes_fulltext")
    op.drop_index("ix_recipes_ingredients_jsonb", "recipes")
    op.drop_index("ix_recipes_tags", "recipes")
    op.drop_index("ix_recipes_ingredient_names", "recipes")
    op.drop_index("ix_recipes_diet_type", "recipes")
    op.drop_index("ix_recipes_course", "recipes")
    op.drop_index("ix_recipes_cuisine", "recipes")
    op.drop_index("ix_recipes_slug", "recipes")
    op.drop_table("recipes")
