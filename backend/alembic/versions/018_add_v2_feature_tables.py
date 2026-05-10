"""Add v2 feature tables: recipe_sources, leftovers, expenses, health_metrics,
guests, and ingredient_substitutions.

Revision ID: 018
Revises: 017
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recipe_sources",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("family_id", UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), index=True),
        sa.Column("dish_node_id", UUID(as_uuid=True), sa.ForeignKey("hcg_nodes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("dish_name", sa.String(255), nullable=False),
        sa.Column("youtube_url", sa.Text, nullable=False),
        sa.Column("channel_name", sa.String(255), nullable=True),
        sa.Column("video_title", sa.String(500), nullable=True),
        sa.Column("contributed_by_id", sa.String(255), nullable=True),
        sa.Column("contributed_by_name", sa.String(255), nullable=True),
        sa.Column("contributed_by_role", sa.String(20), server_default="member"),
        sa.Column("ingredients_extracted", JSONB, nullable=True),
        sa.Column("prep_notes_extracted", sa.Text, nullable=True),
        sa.Column("avg_rating", sa.Float, server_default="0"),
        sa.Column("times_used", sa.Integer, server_default="0"),
        sa.Column("cook_feedback", sa.Text, nullable=True),
        sa.Column("is_cook_approved", sa.Boolean, server_default="false"),
        sa.Column("is_default", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_recipe_sources_family_dish", "recipe_sources", ["family_id", "dish_name"])

    op.create_table(
        "leftovers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("family_id", UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), index=True),
        sa.Column("dish_name", sa.String(255), nullable=False),
        sa.Column("meal_date", sa.Date, nullable=False),
        sa.Column("meal_type", sa.String(20), nullable=False),
        sa.Column("portions_remaining", sa.Integer, server_default="1"),
        sa.Column("reported_by", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("is_consumed", sa.Boolean, server_default="false"),
        sa.Column("consumed_date", sa.Date, nullable=True),
        sa.Column("is_disposed", sa.Boolean, server_default="false"),
        sa.Column("disposed_reason", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "expense_entries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("family_id", UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), index=True),
        sa.Column("cart_id", UUID(as_uuid=True), sa.ForeignKey("carts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("date", sa.Date, index=True, nullable=False),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("category", sa.String(50), server_default="groceries"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("paid_by_id", sa.String(255), nullable=False),
        sa.Column("paid_by_name", sa.String(255), nullable=False),
        sa.Column("split_json", JSONB, nullable=True),
        sa.Column("platform", sa.String(100), nullable=True),
        sa.Column("items_json", JSONB, nullable=True),
        sa.Column("splitwise_expense_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_expense_entries_family_date", "expense_entries", ["family_id", "date"])
    op.create_index("ix_expense_entries_family_category", "expense_entries", ["family_id", "category"])

    op.create_table(
        "expense_settlements",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("family_id", UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), index=True),
        sa.Column("from_member_id", sa.String(255), nullable=False),
        sa.Column("from_member_name", sa.String(255), nullable=False),
        sa.Column("to_member_id", sa.String(255), nullable=False),
        sa.Column("to_member_name", sa.String(255), nullable=False),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("settled", sa.Boolean, server_default="false"),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("month", sa.String(7), nullable=False),
        sa.Column("splitwise_expense_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_expense_settlements_family_month", "expense_settlements", ["family_id", "month"])

    op.create_table(
        "monthly_budgets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("family_id", UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), index=True),
        sa.Column("month", sa.String(7), nullable=False),
        sa.Column("budget_amount", sa.Float, nullable=False),
        sa.Column("category_budgets", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_monthly_budgets_family_month", "monthly_budgets", ["family_id", "month"])

    op.create_table(
        "health_metrics",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("family_id", UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), index=True),
        sa.Column("person_id", sa.String(255), index=True, nullable=False),
        sa.Column("person_name", sa.String(255), nullable=False),
        sa.Column("metric_type", sa.String(50), nullable=False),
        sa.Column("value", sa.Float, nullable=False),
        sa.Column("unit", sa.String(30), nullable=False),
        sa.Column("date_recorded", sa.Date, nullable=False),
        sa.Column("source", sa.String(30), server_default="manual"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("lab_report_json", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_health_metrics_person_type", "health_metrics", ["family_id", "person_id", "metric_type"])
    op.create_index("ix_health_metrics_date", "health_metrics", ["family_id", "date_recorded"])

    op.create_table(
        "guest_profiles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("family_id", UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("dietary_type", sa.String(50), nullable=True),
        sa.Column("allergies", ARRAY(sa.String), nullable=True),
        sa.Column("health_conditions", ARRAY(sa.String), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("visit_count", sa.Integer, server_default="0"),
        sa.Column("last_visit", sa.Date, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "guest_visits",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("family_id", UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), index=True),
        sa.Column("guest_profile_id", UUID(as_uuid=True), sa.ForeignKey("guest_profiles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("guest_name", sa.String(255), nullable=False),
        sa.Column("meal_date", sa.Date, nullable=False),
        sa.Column("meal_type", sa.String(20), nullable=False),
        sa.Column("head_count", sa.Integer, server_default="1"),
        sa.Column("dietary_constraints", JSONB, nullable=True),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_guest_visits_family_date", "guest_visits", ["family_id", "meal_date"])

    op.create_table(
        "ingredient_substitutions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("original_ingredient", sa.String(255), nullable=False),
        sa.Column("substitute_ingredient", sa.String(255), nullable=False),
        sa.Column("compatibility_score", sa.Float, server_default="0.8"),
        sa.Column("flavor_similarity", sa.Float, server_default="0.7"),
        sa.Column("texture_similarity", sa.Float, server_default="0.7"),
        sa.Column("health_benefits", JSONB, nullable=True),
        sa.Column("applicable_conditions", JSONB, nullable=True),
        sa.Column("dish_specific", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("is_global", sa.Boolean, server_default="true"),
        sa.Column("family_id", UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_substitutions_original", "ingredient_substitutions", ["original_ingredient"])
    op.create_index("ix_substitutions_pair", "ingredient_substitutions", ["original_ingredient", "substitute_ingredient"])


def downgrade() -> None:
    op.drop_table("ingredient_substitutions")
    op.drop_table("guest_visits")
    op.drop_table("guest_profiles")
    op.drop_table("health_metrics")
    op.drop_table("monthly_budgets")
    op.drop_table("expense_settlements")
    op.drop_table("expense_entries")
    op.drop_table("leftovers")
    op.drop_table("recipe_sources")
