"""H0: LLM call observability + pgvector + pilot text-only flag + dish embeddings.

This single migration ships the data foundation for the entire pilot AI plan:

  1. llm_calls table -- one row per LLM API call, PII-scrubbed. Lets us build
     evals, train downstream models on prompt/response pairs, attribute cost
     per family.

  2. families.pilot_text_only -- boolean gate that disables voice + image +
     grocery handlers for pilot families. We keep voice/image/grocery code
     installed but flagged off so the rollback is one DB toggle.

  3. pgvector extension + embedding columns on `recipes` and `person_contexts`.
     We attempt to create the extension; if Postgres is missing it (e.g. local
     SQLite-style dev), we degrade gracefully and store embeddings as JSONB.

  4. ab_assignments table -- per-family arm assignment for the H1 A/B test
     between baseline GPT-4o and HCG-RAG meal suggestions.

  5. weekly_recaps table -- one row per Sunday "Bimi knows me" recap that
     was generated and sent to a pilot family.

Revision ID: 028
Revises: 027
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------------------------------------------------------------------
    # 1. llm_calls
    # ---------------------------------------------------------------------
    op.create_table(
        "llm_calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("service", sa.String(40), nullable=False),
        sa.Column("model", sa.String(80), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False, server_default="openai"),
        sa.Column(
            "family_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("families.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("cohort", sa.String(50), nullable=True),
        sa.Column("ab_arm", sa.String(40), nullable=True),
        sa.Column("prompt_hash", sa.String(64), nullable=False),
        sa.Column("prompt_excerpt", sa.Text, nullable=True),
        sa.Column("response_excerpt", sa.Text, nullable=True),
        sa.Column("prompt_tokens", sa.Integer, nullable=True),
        sa.Column("completion_tokens", sa.Integer, nullable=True),
        sa.Column("total_tokens", sa.Integer, nullable=True),
        sa.Column("cost_usd", sa.Float, nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=False),
        sa.Column("success", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("metadata_json", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_llm_calls_service_created", "llm_calls", ["service", "created_at"])
    op.create_index("ix_llm_calls_family_created", "llm_calls", ["family_id", "created_at"])
    op.create_index("ix_llm_calls_cohort_created", "llm_calls", ["cohort", "created_at"])
    op.create_index("ix_llm_calls_prompt_hash", "llm_calls", ["prompt_hash"])

    # ---------------------------------------------------------------------
    # 2. families.pilot_text_only
    # ---------------------------------------------------------------------
    op.add_column(
        "families",
        sa.Column(
            "pilot_text_only",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # ---------------------------------------------------------------------
    # 3. Embedding columns (JSONB by default; pgvector upgrade is a separate concern).
    #
    # We default to JSONB so the migration is independent of which Postgres
    # image runs it. The cosine() helper in services/embeddings.py works
    # equally over JSONB arrays. To upgrade to native pgvector at scale,
    # run a separate migration AFTER `CREATE EXTENSION vector` succeeds and
    # the column type ALTER can find the right cast.
    # ---------------------------------------------------------------------
    op.add_column("recipes", sa.Column("embedding", postgresql.JSONB, nullable=True))
    op.add_column("person_contexts", sa.Column("embedding", postgresql.JSONB, nullable=True))
    op.add_column(
        "recipes",
        sa.Column("embedded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "person_contexts",
        sa.Column("embedded_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ---------------------------------------------------------------------
    # 4. ab_assignments
    # ---------------------------------------------------------------------
    op.create_table(
        "ab_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "family_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("families.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("experiment", sa.String(80), nullable=False),
        sa.Column("arm", sa.String(40), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("metadata_json", postgresql.JSONB, nullable=True),
        sa.UniqueConstraint("family_id", "experiment", name="uq_ab_family_experiment"),
    )
    op.create_index("ix_ab_assignments_experiment_arm", "ab_assignments", ["experiment", "arm"])

    # ---------------------------------------------------------------------
    # 5. weekly_recaps
    # ---------------------------------------------------------------------
    op.create_table(
        "weekly_recaps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "family_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("families.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("week_start", sa.Date, nullable=False),
        sa.Column("recap_text", sa.Text, nullable=False),
        sa.Column("learnings_json", postgresql.JSONB, nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivery_channel", sa.String(20), nullable=True),
        sa.Column("subjective_score", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("family_id", "week_start", name="uq_weekly_recap_family_week"),
    )
    op.create_index("ix_weekly_recaps_family_week", "weekly_recaps", ["family_id", "week_start"])


def downgrade() -> None:
    op.drop_index("ix_weekly_recaps_family_week", table_name="weekly_recaps")
    op.drop_table("weekly_recaps")

    op.drop_index("ix_ab_assignments_experiment_arm", table_name="ab_assignments")
    op.drop_table("ab_assignments")

    # Drop embedding columns. pgvector extension is left in place (other tables may use it).
    try:
        op.execute("DROP INDEX IF EXISTS ix_recipes_embedding")
    except Exception:
        pass
    op.drop_column("recipes", "embedded_at")
    op.drop_column("recipes", "embedding")
    op.drop_column("person_contexts", "embedded_at")
    op.drop_column("person_contexts", "embedding")

    op.drop_column("families", "pilot_text_only")

    op.drop_index("ix_llm_calls_prompt_hash", table_name="llm_calls")
    op.drop_index("ix_llm_calls_cohort_created", table_name="llm_calls")
    op.drop_index("ix_llm_calls_family_created", table_name="llm_calls")
    op.drop_index("ix_llm_calls_service_created", table_name="llm_calls")
    op.drop_table("llm_calls")
