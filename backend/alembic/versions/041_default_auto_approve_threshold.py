"""Default auto_approve_threshold to ₹500 for new and existing families.

Per the 2026-05-03 UX redesign (see bimi/docs/UX-REDESIGN-2026-05-03.md
§11c), the auto-approval mechanism was already in place but the column
default was NULL — meaning every new family had to discover the setting
in 'Trust rules' before any grocery order would auto-approve. Day-1
users instead saw an Approvals queue piling up.

This migration:

  1. Sets the column server_default to '500.0' so newly-created rows
     pick it up at the DB level (not just the ORM level).
  2. Backfills existing NULL rows to 500.0 so production families
     transition silently — no surprise inversions of behaviour.

A user who has explicitly set their threshold to a non-NULL value
(higher or lower) is left untouched — only NULL → 500 is touched.

Revision ID: 041
Revises: 040
"""

import sqlalchemy as sa
from alembic import op


revision = "041"
down_revision = "040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Backfill — only flip rows that are still NULL. Any explicit
    #    user choice (including an explicit NULL re-set after this
    #    runs once) stays untouched on subsequent runs.
    op.execute(
        """
        UPDATE families
        SET auto_approve_threshold = 500.0
        WHERE auto_approve_threshold IS NULL
        """
    )

    # 2. Persist the new server-side default so any future INSERT that
    #    omits the column also gets 500.0.
    op.alter_column(
        "families",
        "auto_approve_threshold",
        server_default=sa.text("500.0"),
    )


def downgrade() -> None:
    # Leave the data backfill in place (no destructive rollback) — but
    # restore the column to NULL-default so the schema matches pre-041.
    op.alter_column(
        "families",
        "auto_approve_threshold",
        server_default=None,
    )
