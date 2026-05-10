"""Add context memory: family context, conversation messages, item rejections, preference extensions

Revision ID: 007
Revises: 006
Create Date: 2026-04-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision: str = "007"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Family-level context store
    op.create_table(
        "family_contexts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("family_id", UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), unique=True),
        sa.Column("health_conditions", ARRAY(sa.String), nullable=True),
        sa.Column("dietary_restrictions", ARRAY(sa.String), nullable=True),
        sa.Column("allergies", ARRAY(sa.String), nullable=True),
        sa.Column("household_size", sa.Integer, nullable=True),
        sa.Column("cooking_style", sa.String(100), nullable=True),
        sa.Column("is_vegetarian", sa.Boolean, server_default="false"),
        sa.Column("preferred_platform", sa.String(50), nullable=True),
        sa.Column("bulk_platform", sa.String(50), nullable=True),
        sa.Column("urgent_platform", sa.String(50), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("custom_context", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Conversation message log for cross-message awareness
    op.create_table(
        "conversation_messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("parent_id", UUID(as_uuid=True), sa.ForeignKey("parents.id", ondelete="CASCADE")),
        sa.Column("family_id", UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE")),
        sa.Column("source_type", sa.String(20)),
        sa.Column("raw_input", sa.Text, nullable=True),
        sa.Column("extracted_items_json", sa.Text, nullable=True),
        sa.Column("confidence", sa.Float, default=0.0),
        sa.Column("was_confirmed", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_conversation_messages_parent_created", "conversation_messages", ["parent_id", "created_at"])

    # Item rejection tracking
    op.create_table(
        "item_rejections",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("family_id", UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE")),
        sa.Column("item_name", sa.String(255)),
        sa.Column("brand", sa.String(255), nullable=True),
        sa.Column("reason", sa.String(50), server_default="rejected"),
        sa.Column("rejection_count", sa.Integer, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_item_rejections_family", "item_rejections", ["family_id", "item_name"])

    # Extend preference_items with substitution + rejection columns
    op.add_column("preference_items", sa.Column("substitute_brands", ARRAY(sa.String), nullable=True))
    op.add_column("preference_items", sa.Column("rejected_brands", ARRAY(sa.String), nullable=True))


def downgrade() -> None:
    op.drop_column("preference_items", "rejected_brands")
    op.drop_column("preference_items", "substitute_brands")
    op.drop_index("ix_item_rejections_family", table_name="item_rejections")
    op.drop_table("item_rejections")
    op.drop_index("ix_conversation_messages_parent_created", table_name="conversation_messages")
    op.drop_table("conversation_messages")
    op.drop_table("family_contexts")
