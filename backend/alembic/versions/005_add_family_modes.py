"""Add family_type, auto_approve, self_use fields

Revision ID: 005
Revises: 004
Create Date: 2026-04-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("families", sa.Column("family_type", sa.String(50), server_default="aging_parent"))
    op.add_column("families", sa.Column("auto_approve_threshold", sa.Float, nullable=True))
    op.add_column("families", sa.Column("self_use", sa.Boolean, server_default="false"))
    op.add_column("parents", sa.Column("is_also_approver", sa.Boolean, server_default="false"))


def downgrade() -> None:
    op.drop_column("parents", "is_also_approver")
    op.drop_column("families", "self_use")
    op.drop_column("families", "auto_approve_threshold")
    op.drop_column("families", "family_type")
