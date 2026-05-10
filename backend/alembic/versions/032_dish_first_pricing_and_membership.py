"""Dish catalog + dish-preference tables.

Originally part of the dish-first Instacook + Gold-membership rollout. The
Instacook pieces (memberships, savings_events, instacook_pool_cooks.skill_tier,
instacook_bookings.* extensions) were stripped when the Instacook marketplace
was retired; this migration is now a pure additive for the dish catalog used
by Your Kitchen.

Tables created:
  - dishes            — the dish catalog (slug, name, portion_tiers, etc.)
  - dish_preferences  — household memory of "we like Dal Tadka spicy"

Revision ID: 032
Revises: 031
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dishes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("cuisine", sa.String(50), nullable=False, server_default="north_indian"),
        sa.Column("meal_types", postgresql.JSONB, nullable=True, server_default="[]"),
        sa.Column("is_veg", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("base_time_minutes", sa.Integer, nullable=False, server_default="40"),
        sa.Column("skill_tier", sa.Integer, nullable=False, server_default="1"),
        sa.Column("portion_tiers", postgresql.JSONB, nullable=False),
        sa.Column("required_ingredients", postgresql.JSONB, nullable=True, server_default="[]"),
        sa.Column("customization_options", postgresql.JSONB, nullable=True, server_default="{}"),
        sa.Column("image_url", sa.String(512), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("display_order", sa.Integer, nullable=False, server_default="100"),
        sa.Column("swiggy_benchmark_captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_dishes_slug", "dishes", ["slug"])
    op.create_index("ix_dishes_is_veg", "dishes", ["is_veg"])
    op.create_index("ix_dishes_is_active", "dishes", ["is_active"])

    op.create_table(
        "dish_preferences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dish_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("dishes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("spice_level", sa.String(20), nullable=True),
        sa.Column("style", sa.String(50), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("customizations", postgresql.JSONB, nullable=True, server_default="{}"),
        sa.Column("times_ordered", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_ordered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("family_id", "dish_id", name="uq_dish_preferences_family_dish"),
    )
    op.create_index("ix_dish_preferences_family_id", "dish_preferences", ["family_id"])
    op.create_index("ix_dish_preferences_dish_id", "dish_preferences", ["dish_id"])


def downgrade() -> None:
    op.drop_index("ix_dish_preferences_dish_id", table_name="dish_preferences")
    op.drop_index("ix_dish_preferences_family_id", table_name="dish_preferences")
    op.drop_table("dish_preferences")

    op.drop_index("ix_dishes_is_active", table_name="dishes")
    op.drop_index("ix_dishes_is_veg", table_name="dishes")
    op.drop_index("ix_dishes_slug", table_name="dishes")
    op.drop_table("dishes")
