"""Add client-driven sync fields to `househelp_absences`.

Slice of the cook-absence two-way sync plan: until now, absences were
created exclusively by WhatsApp ingestion (`record_absence()` from the
webhook), and the mobile app's local Zustand store was the ONLY home
for client-marked absences. This migration closes the schema gap so
the new `POST /absences` and `PATCH /absences/{id}/fallback` endpoints
can persist the richer fields the mobile app already tracks:

  - `end_date`         — multi-day absences (NULL = single day)
  - `affected_meals`   — per-meal absences, e.g. ["lunch"]
                          (NULL = full day)
  - `fallback_chosen`  — what the household decided to do
                          (one of: order_food, self_cook,
                          replacement_cook, instacook, skip)
  - `fallback_details` — free-form note for the fallback
  - `sync_source`      — observability: "whatsapp" | "mobile_app"
                          (helps audit "where did this row come from")

All columns are nullable so existing rows survive the migration with
no backfill. `fallback_chosen` is a free-form String (not a Postgres
ENUM) because the canonical list lives in the frontend's
`CookAbsenceFallback` type and we'd rather validate at the API layer
than churn ENUM values via DDL.

Revision ID: 058
Revises: 057
"""
from alembic import op
import sqlalchemy as sa


revision = "058"
down_revision = "057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "househelp_absences",
        sa.Column("end_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "househelp_absences",
        sa.Column(
            "affected_meals",
            sa.ARRAY(sa.String(length=16)),
            nullable=True,
        ),
    )
    op.add_column(
        "househelp_absences",
        sa.Column("fallback_chosen", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "househelp_absences",
        sa.Column("fallback_details", sa.Text(), nullable=True),
    )
    op.add_column(
        "househelp_absences",
        sa.Column("sync_source", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("househelp_absences", "sync_source")
    op.drop_column("househelp_absences", "fallback_details")
    op.drop_column("househelp_absences", "fallback_chosen")
    op.drop_column("househelp_absences", "affected_meals")
    op.drop_column("househelp_absences", "end_date")
