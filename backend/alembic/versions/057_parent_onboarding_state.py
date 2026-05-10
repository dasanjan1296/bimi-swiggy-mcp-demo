"""Track WhatsApp-native onboarding state on parents.

Slice 5 of the WhatsApp coordination plan: when a household adds a
cook in the app, Bimi sends the cook a confirmation card on WhatsApp
("Aap XYZ ke ghar ki cook hain?"). Their tap on Haan/Galat sets
`onboarded_at` (success) or `is_active = false` (deactivated).

`is_active = false` lets us keep the row for audit/history without
ever dispatching a brief or attendance ping to that number again.
The default is true so existing rows continue to work uninterrupted.

Revision ID: 057
Revises: 056
"""
from alembic import op
import sqlalchemy as sa


revision = "057"
down_revision = "056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "parents",
        sa.Column(
            "onboarded_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "parents",
        sa.Column(
            "is_active",
            sa.Boolean,
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("parents", "is_active")
    op.drop_column("parents", "onboarded_at")
