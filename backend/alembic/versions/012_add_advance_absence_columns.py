"""Add advance absence notice columns to househelp_absences.

Supports advance leave notification with proactive slot polling
for replacement booking on Urban Company and Snabbit.

Revision ID: 012
Revises: 011
Create Date: 2026-04-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "househelp_absences",
        sa.Column("is_advance_notice", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "househelp_absences",
        sa.Column("advance_notice_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "househelp_absences",
        sa.Column("slot_check_active", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "househelp_absences",
        sa.Column("slot_check_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "househelp_absences",
        sa.Column("preferred_platform", sa.String(100), nullable=True),
    )
    op.add_column(
        "househelp_absences",
        sa.Column("slot_found_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "househelp_absences",
        sa.Column("auto_book", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("househelp_absences", "auto_book")
    op.drop_column("househelp_absences", "slot_found_at")
    op.drop_column("househelp_absences", "preferred_platform")
    op.drop_column("househelp_absences", "slot_check_count")
    op.drop_column("househelp_absences", "slot_check_active")
    op.drop_column("househelp_absences", "advance_notice_date")
    op.drop_column("househelp_absences", "is_advance_notice")
