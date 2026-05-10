"""Add delivery tracking fields to carts + new statuses

Revision ID: 004
Revises: 003
Create Date: 2026-04-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("carts", sa.Column("ordered_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("carts", sa.Column("delivery_platform", sa.String(100), nullable=True))
    op.add_column("carts", sa.Column("delivery_eta", sa.String(100), nullable=True))
    op.add_column("carts", sa.Column("delivery_slot", sa.String(200), nullable=True))
    op.add_column("carts", sa.Column("tracking_link", sa.Text, nullable=True))
    op.add_column("carts", sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True))

    op.execute("ALTER TYPE cartstatus ADD VALUE IF NOT EXISTS 'out_for_delivery'")
    op.execute("ALTER TYPE cartstatus ADD VALUE IF NOT EXISTS 'delivered'")


def downgrade() -> None:
    op.drop_column("carts", "delivered_at")
    op.drop_column("carts", "tracking_link")
    op.drop_column("carts", "delivery_slot")
    op.drop_column("carts", "delivery_eta")
    op.drop_column("carts", "delivery_platform")
    op.drop_column("carts", "ordered_at")
