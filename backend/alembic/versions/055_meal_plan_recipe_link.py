"""Attach a chosen recipe link + lock timestamp to each MealPlan.

The household curates YouTube/Instagram links for dishes via WhatsApp
(Slice 1 of the WhatsApp coordination plan). When a meal plan is
created we resolve the family's most-recent default `RecipeSource` for
the dish and pin it on the plan via `recipe_source_id`. Members can
swap it through the app or WhatsApp until the cook gets briefed.

`recipe_locked_at` is set the moment the cook brief carrying the link
goes out — switching after that point is rejected (the cook has
already been told what to make from where).

Revision ID: 055
Revises: 054
"""
from alembic import op
import sqlalchemy as sa


revision = "055"
down_revision = "054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "meal_plans",
        sa.Column(
            "recipe_source_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("recipe_sources.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "meal_plans",
        sa.Column(
            "recipe_locked_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("meal_plans", "recipe_locked_at")
    op.drop_column("meal_plans", "recipe_source_id")
