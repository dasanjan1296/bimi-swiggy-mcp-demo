"""Create meal_votes + otp_codes tables (close model<->migration drift).

Both models existed in `app/models/` but had no Alembic migration:

  - `meal_votes` was created on first run via SQLAlchemy's
    `Base.metadata.create_all` from the seed script.
  - `otp_codes` was created lazily by the FastAPI lifespan via
    `OtpCode.__table__.create(c, checkfirst=True)`.

Both worked but left the schema invisible to Alembic and broke the
"every model has a migration" reflection test. This migration creates
both tables for real.

Revision ID: 042
Revises: 041
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "042"
down_revision = "041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- meal_votes ----
    op.create_table(
        "meal_votes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "family_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("families.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("member_id", sa.String(255), nullable=False),
        sa.Column("member_name", sa.String(255), nullable=False),
        sa.Column("meal_date", sa.String(20), nullable=False),
        sa.Column("meal_type", sa.String(20), nullable=False),
        sa.Column("dish_name", sa.String(500), nullable=False),
        sa.Column("rating", sa.Integer, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_meal_votes_family_meal", "meal_votes", ["family_id", "meal_date", "meal_type"])

    # ---- otp_codes ----
    op.create_table(
        "otp_codes",
        sa.Column("phone", sa.String(20), primary_key=True),
        sa.Column("code", sa.String(10), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("daily_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("daily_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_otp_codes_expires_at", "otp_codes", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_otp_codes_expires_at", table_name="otp_codes")
    op.drop_table("otp_codes")
    op.drop_index("ix_meal_votes_family_meal", table_name="meal_votes")
    op.drop_table("meal_votes")
