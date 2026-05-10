"""Add person_contexts table for Layer 1 of three-layer context architecture.

Each person (parent, child, flatmate, cook, maid) gets their own context record
with dietary preferences, health conditions, allergies, schedule rules, fitness
goals, and behavioral patterns. This replaces the family-level dietary fields
and enables per-person AI customization.

Revision ID: 014
Revises: 013
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

revision = "014"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "person_contexts",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("parent_id", sa.UUID(), sa.ForeignKey("parents.id"), nullable=True, unique=True),
        sa.Column("child_id", sa.UUID(), sa.ForeignKey("children.id"), nullable=True, unique=True),
        sa.Column("family_id", sa.UUID(), sa.ForeignKey("families.id"), nullable=False),
        sa.Column("person_name", sa.String(100), nullable=False, server_default=""),

        # Dietary
        sa.Column("diet_type", sa.String(30), nullable=False, server_default="not_set"),
        sa.Column("dietary_restrictions", ARRAY(sa.String), nullable=True),
        sa.Column("allergies", ARRAY(sa.String), nullable=True),
        sa.Column("health_conditions", ARRAY(sa.String), nullable=True),

        # Behavioral
        sa.Column("typical_order_time", sa.String(20), nullable=True),
        sa.Column("communication_style", sa.String(20), nullable=True),
        sa.Column("language_preference", sa.String(10), nullable=False, server_default="hi"),
        sa.Column("correction_history", JSONB, nullable=True),

        # Schedule
        sa.Column("schedule_rules", JSONB, nullable=True),

        # Fitness/Nutrition
        sa.Column("fitness_goal", sa.String(50), nullable=True),
        sa.Column("nutrition_targets", JSONB, nullable=True),

        # Favorites
        sa.Column("favorite_dishes", ARRAY(sa.String), nullable=True),
        sa.Column("disliked_dishes", ARRAY(sa.String), nullable=True),

        # Metadata
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),

        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_person_contexts_family_id", "person_contexts", ["family_id"])
    op.create_index("ix_person_contexts_parent_id", "person_contexts", ["parent_id"])
    op.create_index("ix_person_contexts_child_id", "person_contexts", ["child_id"])


def downgrade() -> None:
    op.drop_index("ix_person_contexts_child_id")
    op.drop_index("ix_person_contexts_parent_id")
    op.drop_index("ix_person_contexts_family_id")
    op.drop_table("person_contexts")
