"""Add chef inspiration columns to dishes.

Each dish now cites a master chef's publicly available recipe (e.g. Ranveer
Brar's Butter Chicken, Bong Eats' Kosha Mangsho). We store the chef name, the
recipe title, a YouTube *search* URL (survives takedowns), and the platform
label. All four are non-null with empty-string defaults so existing rows and
older clients continue to work unchanged.

Revision ID: 037
Revises: 036
"""

from alembic import op
import sqlalchemy as sa


revision = "037"
down_revision = "033"
branch_labels = None
depends_on = None


_COLUMNS = [
    ("inspired_by_chef", 255),
    ("inspired_by_title", 255),
    ("inspired_by_url", 512),
    ("inspired_by_platform", 32),
]


def upgrade() -> None:
    for name, length in _COLUMNS:
        op.add_column(
            "dishes",
            sa.Column(
                name,
                sa.String(length=length),
                nullable=False,
                server_default="",
            ),
        )


def downgrade() -> None:
    for name, _ in reversed(_COLUMNS):
        op.drop_column("dishes", name)
