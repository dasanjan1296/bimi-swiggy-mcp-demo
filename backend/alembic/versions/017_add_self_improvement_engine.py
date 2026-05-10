"""Add Self-Improvement Engine tables (standing_instructions, communication_profiles,
improvement_logs, proactive_suggestions).

Revision ID: 017
Revises: 016
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- Standing Instructions --
    op.create_table(
        "standing_instructions",
        sa.Column("id", UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("family_id", UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by_type", sa.String(10), nullable=False),
        sa.Column("created_by_id", UUID(as_uuid=True), nullable=False),
        sa.Column("target_role", sa.String(20), nullable=False, server_default="cook"),
        sa.Column("instruction_text", sa.Text(), nullable=False),
        sa.Column("structured_action", JSONB, nullable=True),
        sa.Column("recurrence", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("category", sa.String(30), nullable=False, server_default="custom"),
        sa.Column("priority", sa.String(20), nullable=False, server_default="normal"),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("compliance_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("skip_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_standing_instructions_family_status", "standing_instructions", ["family_id", "status"])
    op.create_index("ix_standing_instructions_family_target", "standing_instructions", ["family_id", "target_role"])

    # -- Communication Profiles --
    op.create_table(
        "communication_profiles",
        sa.Column("id", UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("family_id", UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), nullable=False),
        sa.Column("person_type", sa.String(10), nullable=False),
        sa.Column("person_id", UUID(as_uuid=True), nullable=False),
        sa.Column("preferred_message_length", sa.String(20), nullable=False, server_default="moderate"),
        sa.Column("preferred_language_mix", sa.Float(), nullable=False, server_default=sa.text("0.3")),
        sa.Column("message_format_preference", sa.String(20), nullable=False, server_default="buttons"),
        sa.Column("tone", sa.String(20), nullable=False, server_default="friendly"),
        sa.Column("emoji_density", sa.Float(), nullable=False, server_default=sa.text("0.5")),
        sa.Column("optimal_contact_times", JSONB, nullable=True),
        sa.Column("response_latency_avg_seconds", sa.Integer(), nullable=False, server_default=sa.text("300")),
        sa.Column("ignore_rate", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("confirmation_accuracy", sa.Float(), nullable=False, server_default=sa.text("0.7")),
        sa.Column("vocabulary_level", JSONB, nullable=True),
        sa.Column("escalation_threshold", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column("total_messages_sent", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_messages_received", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_corrections", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_ignores", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_profiled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_comm_profile_person", "communication_profiles", ["person_type", "person_id"], unique=True)
    op.create_index("ix_comm_profile_family", "communication_profiles", ["family_id"])

    # -- Improvement Logs --
    op.create_table(
        "improvement_logs",
        sa.Column("id", UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("family_id", UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), nullable=False),
        sa.Column("triggered_by_type", sa.String(10), nullable=False),
        sa.Column("triggered_by_id", UUID(as_uuid=True), nullable=True),
        sa.Column("trigger_event", sa.Text(), nullable=False),
        sa.Column("category", sa.String(30), nullable=False, server_default="general"),
        sa.Column("parameter_changed", sa.String(255), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default=sa.text("0.5")),
        sa.Column("auto_applied", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("reverted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("reverted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revert_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_improvement_logs_family_category", "improvement_logs", ["family_id", "category"])
    op.create_index("ix_improvement_logs_family_created", "improvement_logs", ["family_id", "created_at"])

    # -- Proactive Suggestions --
    op.create_table(
        "proactive_suggestions",
        sa.Column("id", UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("family_id", UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pattern_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence", JSONB, nullable=True),
        sa.Column("suggested_action", JSONB, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default=sa.text("0.5")),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_proactive_suggestions_family_status", "proactive_suggestions", ["family_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_proactive_suggestions_family_status")
    op.drop_table("proactive_suggestions")
    op.drop_index("ix_improvement_logs_family_created")
    op.drop_index("ix_improvement_logs_family_category")
    op.drop_table("improvement_logs")
    op.drop_index("ix_comm_profile_family")
    op.drop_index("ix_comm_profile_person")
    op.drop_table("communication_profiles")
    op.drop_index("ix_standing_instructions_family_target")
    op.drop_index("ix_standing_instructions_family_status")
    op.drop_table("standing_instructions")
