"""Initial schema

Revision ID: 001
Revises: None
Create Date: 2026-04-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "families",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "parents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(20), unique=True, nullable=False),
        sa.Column("language", sa.String(20), server_default="hi"),
        sa.Column("whatsapp_id", sa.String(50), unique=True, nullable=False),
    )

    op.create_table(
        "children",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(20), unique=True, nullable=False),
        sa.Column("fcm_token", sa.String(512), nullable=True),
        sa.Column("domains", postgresql.ARRAY(sa.String), nullable=True),
        sa.Column("password_hash", sa.String(255), server_default=""),
    )

    op.create_table(
        "preference_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_name", sa.String(255), nullable=False),
        sa.Column("brand", sa.String(255), nullable=True),
        sa.Column("quantity", sa.Float, server_default="1.0"),
        sa.Column("unit", sa.String(50), server_default="pcs"),
        sa.Column("frequency_days", sa.Integer, nullable=True),
        sa.Column("last_ordered", sa.DateTime(timezone=True), nullable=True),
        sa.Column("order_count", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    cart_status = postgresql.ENUM(
        "accumulating", "pending_approval", "approved", "ordered", "skipped", "expired",
        name="cartstatus", create_type=True,
    )

    op.create_table(
        "carts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", cart_status, server_default="accumulating"),
        sa.Column("estimated_total", sa.Float, server_default="0.0"),
        sa.Column("best_platform", sa.String(100), nullable=True),
        sa.Column("deep_link", sa.Text, nullable=True),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("item_count", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "cart_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("cart_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("carts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("brand", sa.String(255), nullable=True),
        sa.Column("quantity", sa.Float, server_default="1.0"),
        sa.Column("unit", sa.String(50), server_default="pcs"),
        sa.Column("urgent", sa.Boolean, server_default="false"),
        sa.Column("prices_json", sa.Text, nullable=True),
        sa.Column("best_platform", sa.String(100), nullable=True),
        sa.Column("best_price", sa.Float, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("cart_items")
    op.drop_table("carts")
    op.execute("DROP TYPE IF EXISTS cartstatus")
    op.drop_table("preference_items")
    op.drop_table("children")
    op.drop_table("parents")
    op.drop_table("families")
