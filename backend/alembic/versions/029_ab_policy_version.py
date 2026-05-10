"""F20: ab_assignments.policy_version column.

Lets us reassign families when an A/B experiment's config changes (e.g. when
we add a new arm or rebalance the split). Without this column, a family
that joined under v1 stays in the v1 arm even after we bump to v2.

Revision ID: 029
Revises: 028
"""

from alembic import op
import sqlalchemy as sa

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ab_assignments",
        sa.Column(
            "policy_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    op.create_index(
        "ix_ab_assignments_experiment_version",
        "ab_assignments",
        ["experiment", "policy_version"],
    )


def downgrade() -> None:
    op.drop_index("ix_ab_assignments_experiment_version", table_name="ab_assignments")
    op.drop_column("ab_assignments", "policy_version")
