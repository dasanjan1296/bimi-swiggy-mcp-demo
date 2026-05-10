"""Two-basket grocery automation (Swiggy Instamart only).

Originally combined the multi-platform UC-removal cleanup with new
grocery-basket tables. The platform-session and service-booking pieces
went away when the multi-platform commerce stack was retired; what
remains is the additive part:

  - Family-level grocery automation settings.
  - weekly_baskets (deep-link bulk basket).
  - topup_baskets (perishable batched orders).

Revision ID: 026
Revises: 025
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- Family-level grocery automation settings ----
    op.add_column(
        "families",
        sa.Column("max_orders_per_week", sa.Integer, nullable=False, server_default="3"),
    )
    op.add_column(
        "families",
        sa.Column("max_delivery_fee_ratio", sa.Float, nullable=False, server_default="0.15"),
    )
    op.add_column(
        "families",
        sa.Column("weekly_bulk_day", sa.String(10), nullable=False, server_default="sunday"),
    )
    op.add_column(
        "families",
        sa.Column("weekly_bulk_min_total", sa.Float, nullable=False, server_default="800"),
    )
    op.add_column(
        "families",
        sa.Column("default_upi_vpa", sa.String(255), nullable=True),
    )

    # ---- Two-basket grocery model ----
    op.create_table(
        "weekly_baskets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="collecting"),
        # collecting | scheduled | sent_to_user | completed | cancelled
        sa.Column("items_json", sa.Text, nullable=False, server_default="[]"),
        sa.Column("estimated_total", sa.Float, nullable=False, server_default="0"),
        sa.Column("platform_id", sa.String(50), nullable=True),
        sa.Column("deep_link_url", sa.Text, nullable=True),
        sa.Column("target_delivery_day", sa.Date, nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_weekly_baskets_family_status", "weekly_baskets", ["family_id", "status"])

    op.create_table(
        "topup_baskets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("families.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="collecting"),
        # collecting | ready_to_order | placed | delivered | failed | cancelled
        sa.Column("items_json", sa.Text, nullable=False, server_default="[]"),
        sa.Column("triggered_by_meal_plan_ids", postgresql.JSONB, nullable=True),
        sa.Column("batch_window_open_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("batch_window_close_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("platform_id", sa.String(50), nullable=True),
        sa.Column("cart_total", sa.Float, nullable=True),
        sa.Column("delivery_fee", sa.Float, nullable=True),
        sa.Column("delivery_efficiency_ratio", sa.Float, nullable=True),
        sa.Column("platform_order_id", sa.String(100), nullable=True),
        sa.Column("tracking_url", sa.Text, nullable=True),
        sa.Column("payment_method", sa.String(50), nullable=True),
        sa.Column("payment_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("placed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_topup_baskets_family_status", "topup_baskets", ["family_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_topup_baskets_family_status", table_name="topup_baskets")
    op.drop_table("topup_baskets")
    op.drop_index("ix_weekly_baskets_family_status", table_name="weekly_baskets")
    op.drop_table("weekly_baskets")

    op.drop_column("families", "default_upi_vpa")
    op.drop_column("families", "weekly_bulk_min_total")
    op.drop_column("families", "weekly_bulk_day")
    op.drop_column("families", "max_delivery_fee_ratio")
    op.drop_column("families", "max_orders_per_week")
