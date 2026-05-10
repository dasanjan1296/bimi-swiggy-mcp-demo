"""Add Household Context Graph tables (hcg_nodes, hcg_edges, hcg_snapshots, know_me_sessions).

Revision ID: 016
Revises: 015
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hcg_nodes",
        sa.Column("id", UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("family_id", UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_type", sa.String(30), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("canonical_name", sa.String(255), nullable=False),
        sa.Column("metadata_json", JSONB, nullable=True),
        sa.Column("is_global", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("family_id", "node_type", "canonical_name", name="uq_hcg_node_family_type_name"),
    )
    op.create_index("ix_hcg_nodes_family_type", "hcg_nodes", ["family_id", "node_type"])

    op.create_table(
        "hcg_edges",
        sa.Column("id", UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("family_id", UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), nullable=False),
        # Subject
        sa.Column("subject_type", sa.String(10), nullable=False),
        sa.Column("subject_person_id", UUID(as_uuid=True), nullable=True),
        sa.Column("subject_node_id", UUID(as_uuid=True), sa.ForeignKey("hcg_nodes.id", ondelete="CASCADE"), nullable=True),
        # Object
        sa.Column("object_type", sa.String(10), nullable=False),
        sa.Column("object_person_id", UUID(as_uuid=True), nullable=True),
        sa.Column("object_node_id", UUID(as_uuid=True), sa.ForeignKey("hcg_nodes.id", ondelete="CASCADE"), nullable=True),
        # Relation
        sa.Column("relation_type", sa.String(30), nullable=False),
        # Confidence system
        sa.Column("confidence", sa.Float(), nullable=False, server_default=sa.text("0.5")),
        sa.Column("strength", sa.Float(), nullable=False, server_default=sa.text("0.5")),
        sa.Column("source_modality", sa.String(20), nullable=False, server_default="implicit"),
        sa.Column("safety_class", sa.String(20), nullable=False, server_default="preference"),
        # Bayesian state
        sa.Column("alpha", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("beta_param", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("observation_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        # Temporal
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_confirmed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        # Causal ancestry
        sa.Column("causal_ancestor", sa.Text(), nullable=True),
        sa.Column("causal_edge_id", UUID(as_uuid=True), sa.ForeignKey("hcg_edges.id", ondelete="SET NULL"), nullable=True),
        # Seasonal pattern
        sa.Column("seasonal_pattern", JSONB, nullable=True),
        # CUSUM drift detection
        sa.Column("cusum_pos", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("cusum_neg", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("cusum_reference", sa.Float(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "(subject_person_id IS NOT NULL) OR (subject_node_id IS NOT NULL)",
            name="ck_hcg_edge_subject",
        ),
        sa.CheckConstraint(
            "(object_person_id IS NOT NULL) OR (object_node_id IS NOT NULL)",
            name="ck_hcg_edge_object",
        ),
    )
    op.create_index("ix_hcg_edges_family", "hcg_edges", ["family_id"])
    op.create_index("ix_hcg_edges_subject_person", "hcg_edges", ["family_id", "subject_person_id"])
    op.create_index("ix_hcg_edges_object_node", "hcg_edges", ["family_id", "object_node_id"])
    op.create_index("ix_hcg_edges_relation", "hcg_edges", ["family_id", "relation_type"])
    op.create_index("ix_hcg_edges_subject_node", "hcg_edges", ["subject_node_id"])

    op.create_table(
        "hcg_snapshots",
        sa.Column("id", UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("edge_id", UUID(as_uuid=True), sa.ForeignKey("hcg_edges.id", ondelete="CASCADE"), nullable=False),
        sa.Column("confidence_before", sa.Float(), nullable=False),
        sa.Column("confidence_after", sa.Float(), nullable=False),
        sa.Column("strength_before", sa.Float(), nullable=False),
        sa.Column("strength_after", sa.Float(), nullable=False),
        sa.Column("change_reason", sa.String(30), nullable=False),
        sa.Column("change_details", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_hcg_snapshots_edge", "hcg_snapshots", ["edge_id"])

    op.create_table(
        "know_me_sessions",
        sa.Column("id", UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("family_id", UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), nullable=False),
        sa.Column("person_id", UUID(as_uuid=True), nullable=True),
        sa.Column("session_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="in_progress"),
        sa.Column("questions_asked", JSONB, nullable=True),
        sa.Column("edges_created", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("edges_updated", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("trigger_reason", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_know_me_sessions_family", "know_me_sessions", ["family_id"])


def downgrade() -> None:
    op.drop_index("ix_know_me_sessions_family")
    op.drop_table("know_me_sessions")
    op.drop_index("ix_hcg_snapshots_edge")
    op.drop_table("hcg_snapshots")
    op.drop_index("ix_hcg_edges_subject_node")
    op.drop_index("ix_hcg_edges_relation")
    op.drop_index("ix_hcg_edges_object_node")
    op.drop_index("ix_hcg_edges_subject_person")
    op.drop_index("ix_hcg_edges_family")
    op.drop_table("hcg_edges")
    op.drop_index("ix_hcg_nodes_family_type")
    op.drop_table("hcg_nodes")
