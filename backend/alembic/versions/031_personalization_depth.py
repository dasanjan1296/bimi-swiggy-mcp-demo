"""Personalization depth columns: G2 + G6 + G7 + G8.

  G2  family_contexts.meal_time_slots JSONB         -- per-family clock for breakfast/lunch/dinner/snack
  G6  family_contexts.variety_preference float       -- 0=consistency, 1=high variety
  G7  family_contexts.regional_preferences ARRAY     -- ['punjabi', 'tamil', 'bengali', ...]
  G7  recipes.regional_cuisine String                -- finer than the existing `cuisine` column
  G8  person_contexts.spice_level int                -- 1 (none) .. 5 (very spicy)
  G8  person_contexts.portion_multiplier float       -- 0.3 .. 2.0 (relative to a default adult portion)

These power Phase G ranker improvements. Backfill defaults are sane:
meal slots default to 7:30 / 13:00 / 20:00 IST; variety_preference defaults
to 0.5 (Thompson default); spice_level defaults to 3; portion_multiplier
defaults to 1.0.

Revision ID: 031
Revises: 030
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None

DEFAULT_MEAL_SLOTS = '{"breakfast": "07:30", "lunch": "13:00", "dinner": "20:00", "snack": "17:00"}'


def upgrade() -> None:
    # G2 + G6 + G7 on family_contexts
    op.add_column(
        "family_contexts",
        sa.Column(
            "meal_time_slots",
            postgresql.JSONB,
            nullable=True,
            server_default=sa.text(f"'{DEFAULT_MEAL_SLOTS}'::jsonb"),
        ),
    )
    op.add_column(
        "family_contexts",
        sa.Column(
            "variety_preference",
            sa.Float,
            nullable=False,
            server_default=sa.text("0.5"),
        ),
    )
    op.add_column(
        "family_contexts",
        sa.Column(
            "regional_preferences",
            postgresql.ARRAY(sa.String),
            nullable=True,
        ),
    )

    # G7 on recipes
    op.add_column(
        "recipes",
        sa.Column("regional_cuisine", sa.String(50), nullable=True),
    )
    op.create_index("ix_recipes_regional_cuisine", "recipes", ["regional_cuisine"])

    # G8 on person_contexts
    op.add_column(
        "person_contexts",
        sa.Column("spice_level", sa.Integer, nullable=False, server_default=sa.text("3")),
    )
    op.add_column(
        "person_contexts",
        sa.Column(
            "portion_multiplier",
            sa.Float,
            nullable=False,
            server_default=sa.text("1.0"),
        ),
    )


def downgrade() -> None:
    op.drop_column("person_contexts", "portion_multiplier")
    op.drop_column("person_contexts", "spice_level")
    op.drop_index("ix_recipes_regional_cuisine", table_name="recipes")
    op.drop_column("recipes", "regional_cuisine")
    op.drop_column("family_contexts", "regional_preferences")
    op.drop_column("family_contexts", "variety_preference")
    op.drop_column("family_contexts", "meal_time_slots")
