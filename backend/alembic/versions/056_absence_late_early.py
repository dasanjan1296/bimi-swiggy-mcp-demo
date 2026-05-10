"""Track late arrivals and early departures on `househelp_absences`.

Slice 2 of the WhatsApp coordination plan: cooks now confirm
attendance via a 6:30 AM check-in card with three buttons (Haan /
Nahi / Late). The "Late" branch asks for an ETA which is stored
here. Separately, when a cook proactively says "2 baje nikal jaungi"
or "doctor jaana hai", we record `early_leave_time`.

A row with just `late_arrival_time` or `early_leave_time` set (and no
full-day absence) represents a partial-day deviation — the household
isn't losing the cook for the day, just for part of it. The replacement
booking pipeline (Insta-cook etc.) is intentionally NOT triggered for
partial-day deviations per product spec.

Revision ID: 056
Revises: 055
"""
from alembic import op
import sqlalchemy as sa


revision = "056"
down_revision = "055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "househelp_absences",
        sa.Column("late_arrival_time", sa.Time(), nullable=True),
    )
    op.add_column(
        "househelp_absences",
        sa.Column("early_leave_time", sa.Time(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("househelp_absences", "early_leave_time")
    op.drop_column("househelp_absences", "late_arrival_time")
