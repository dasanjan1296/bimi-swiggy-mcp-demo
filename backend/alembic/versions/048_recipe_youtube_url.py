"""Add a direct youtube_url column to the recipes table.

The existing schema has `youtube_search_query` which is fine when the
client wants to perform a runtime search, but the new "Self cook ideas"
modal on the home screen surfaces curated quick recipes with hand-picked
video links — we want a deterministic URL the FE can hand straight to
`Linking.openURL` rather than reverse-engineering a YouTube search.
This column is nullable so existing rows are unaffected; only the
quick-recipe seeds (loop 13 follow-up migration 049) populate it.

Revision ID: 048
Revises: 047
"""
from alembic import op
import sqlalchemy as sa


revision = "048"
down_revision = "047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "recipes",
        sa.Column("youtube_url", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("recipes", "youtube_url")
