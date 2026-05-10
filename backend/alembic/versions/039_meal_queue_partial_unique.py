"""Fix meal_queue uniqueness — should only constrain active rows.

Migration 038 declared a full UniqueConstraint on
`(family_id, dish_id, queued_by_person_id, status)`. The intent was "at most
one ACTIVE queue entry per (family, dish, member)" — soft-removed and expired
rows should freely coexist for audit. The full constraint blocked
status='active' → status='removed' transitions whenever any older 'removed'
row already existed for the same key, surfacing as a 500 from
`DELETE /your-kitchen/queue/{id}`.

Replace the table-level constraint with a partial unique INDEX whose WHERE
clause limits enforcement to active rows. Postgres supports this directly via
`CREATE UNIQUE INDEX ... WHERE`.

Revision ID: 039
Revises: 038
"""

from alembic import op
import sqlalchemy as sa


revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_meal_queue_active_per_member",
        "meal_queue",
        type_="unique",
    )
    op.create_index(
        "uq_meal_queue_active_per_member",
        "meal_queue",
        ["family_id", "dish_id", "queued_by_person_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index("uq_meal_queue_active_per_member", table_name="meal_queue")
    op.create_unique_constraint(
        "uq_meal_queue_active_per_member",
        "meal_queue",
        ["family_id", "dish_id", "queued_by_person_id", "status"],
    )
