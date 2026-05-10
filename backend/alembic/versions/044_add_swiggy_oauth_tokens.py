"""Per-family Swiggy MCP OAuth token storage.

Replaces the in-memory `_token_store` dict in `routers/swiggy_auth.py`
with a DB-backed, encrypted-at-rest, per-family table. See the model
docstring for schema notes.

Revision ID: 044
Revises: 043
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "044"
down_revision = "043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "swiggy_oauth_tokens",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "family_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("families.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("access_token_ct", sa.LargeBinary, nullable=False),
        sa.Column("access_token_nonce", sa.LargeBinary, nullable=False),
        sa.Column("refresh_token_ct", sa.LargeBinary, nullable=True),
        sa.Column("refresh_token_nonce", sa.LargeBinary, nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scopes", sa.String(255), nullable=False, server_default=""),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_swiggy_oauth_tokens_family_id",
        "swiggy_oauth_tokens",
        ["family_id"],
    )
    # Partial-unique: only one active token per family at any time.
    op.create_index(
        "ix_swiggy_oauth_tokens_family_active",
        "swiggy_oauth_tokens",
        ["family_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_swiggy_oauth_tokens_family_active",
        table_name="swiggy_oauth_tokens",
    )
    op.drop_index(
        "ix_swiggy_oauth_tokens_family_id",
        table_name="swiggy_oauth_tokens",
    )
    op.drop_table("swiggy_oauth_tokens")
