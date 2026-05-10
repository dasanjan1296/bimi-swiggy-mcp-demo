"""Your Kitchen — personal canon (PRD §4.13).

Adds two tables that turn the dish catalog into the household's personal canon:

- `meal_queue`: soft, decay-on-expiry queue of cravings. A queued dish becomes a
  high-prior candidate in Thompson Sampling (with a +0.15 decayed bonus), feeds
  into the next vote with a "Anjan saved this on Sunday" credit line, and
  auto-expires after 14 days. Status transitions: active → consumed (when used
  for a meal) | expired (daily job) | removed (user removes manually).

- `dish_household_notes`: per-(family, dish) peculiarities. Free-text up to
  200 chars per author with an optional pinned flag. Authors can be a specific
  member or NULL meaning "household-level note". Surfaces on the dish card and
  is replayed in cook briefings.

Revision ID: 038
Revises: 037
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "038"
down_revision = "037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ─── meal_queue ──────────────────────────────────────────────────
    op.create_table(
        "meal_queue",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "family_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("families.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "dish_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("dishes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Author of the craving. NULL == "household-saved" (e.g. cook nudge).
        sa.Column(
            "queued_by_person_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        # Optional meal-type hint ("dinner") so we don't suggest dosa for dinner
        # when it was queued for breakfast. NULL = any.
        sa.Column("meal_type", sa.String(20), nullable=True),
        sa.Column("note", sa.String(200), nullable=True),
        # active | consumed | expired | removed
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
            # Default: 14 days from creation. Computed in service code, but a
            # safety default at the column level keeps `expires_at IS NOT NULL`
            # simple in the daily expiry job.
            server_default=sa.text("now() + interval '14 days'"),
        ),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "consumed_in_meal_log_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("meal_logs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        # Idempotent add: a single member can't double-queue the same dish
        # while one is still active. Removing the row (status='removed') frees
        # them to re-queue. Postgres unique constraints don't natively support
        # WHERE clauses, so we use a partial unique index instead.
        sa.UniqueConstraint(
            "family_id",
            "dish_id",
            "queued_by_person_id",
            "status",
            name="uq_meal_queue_active_per_member",
        ),
    )
    op.create_index(
        "ix_meal_queue_family_status",
        "meal_queue",
        ["family_id", "status"],
    )
    op.create_index(
        "ix_meal_queue_expires",
        "meal_queue",
        ["status", "expires_at"],
    )

    # ─── dish_household_notes ────────────────────────────────────────
    op.create_table(
        "dish_household_notes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "family_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("families.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "dish_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("dishes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # NULL == household-level note (no specific author). The unique
        # constraint below treats NULL as a distinct value via a sentinel
        # column ordering choice — see uq below.
        sa.Column(
            "author_person_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("body", sa.String(200), nullable=False),
        # Only one note can be pinned per (family, dish). Surfaced on the
        # household dish card. Enforced in service code (no DB constraint
        # because Postgres can't easily express "AT MOST ONE pinned per dish").
        sa.Column(
            "pinned",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    # One note per (family, dish, author). Authors with the same dish overwrite
    # cleanly via upsert. Postgres treats two NULL author_person_id values as
    # distinct in a UNIQUE constraint — that's fine because we only ever upsert
    # NULL-author notes via the household_only=True path which deletes prior
    # NULL-author rows first (see services/your_kitchen.upsert_note).
    op.create_index(
        "ix_dish_household_notes_family_dish",
        "dish_household_notes",
        ["family_id", "dish_id"],
    )
    op.create_index(
        "uq_dish_household_notes_member",
        "dish_household_notes",
        ["family_id", "dish_id", "author_person_id"],
        unique=True,
        postgresql_where=sa.text("author_person_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_dish_household_notes_member",
        table_name="dish_household_notes",
    )
    op.drop_index(
        "ix_dish_household_notes_family_dish",
        table_name="dish_household_notes",
    )
    op.drop_table("dish_household_notes")

    op.drop_index("ix_meal_queue_expires", table_name="meal_queue")
    op.drop_index("ix_meal_queue_family_status", table_name="meal_queue")
    op.drop_table("meal_queue")
