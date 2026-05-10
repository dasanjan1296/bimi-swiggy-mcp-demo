"""Extend recipe_sources with source_platform, thumbnail, description for suggest-a-dish.

Revision ID: 025
Revises: 024
"""
from alembic import op
import sqlalchemy as sa

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("recipe_sources", sa.Column("source_platform", sa.String(20), server_default="youtube", nullable=False))
    op.add_column("recipe_sources", sa.Column("thumbnail_url", sa.Text(), nullable=True))
    op.add_column("recipe_sources", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("recipe_sources", sa.Column("note_for_cook", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("recipe_sources", "note_for_cook")
    op.drop_column("recipe_sources", "description")
    op.drop_column("recipe_sources", "thumbnail_url")
    op.drop_column("recipe_sources", "source_platform")
