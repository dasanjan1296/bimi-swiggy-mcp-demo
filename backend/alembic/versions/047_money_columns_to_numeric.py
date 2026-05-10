"""Loop 12: convert money columns from Float to Numeric(10, 2).

Float arithmetic is not decimal-exact: 0.1 + 0.2 == 0.30000000000000004.
For invoices that need to reconcile against Swiggy's authoritative
ledger, we need exact decimal storage. We keep `asdecimal=False` at the
SQLAlchemy layer so callers continue to receive Python floats — the win
here is at the storage + SQL-comparison layer.

Columns converted:
  - carts.estimated_total
  - cart_items.best_price
  - weekly_grocery_baskets.estimated_total
  - basket_orders.cart_total
  - basket_orders.delivery_fee
  - expense_entries.amount
  - expense_settlements.amount
  - monthly_budgets.budget_amount
  - auto_approval_rules.max_amount
  - families.weekly_bulk_min_total

Revision ID: 047
Revises: 046
"""

from alembic import op
import sqlalchemy as sa


revision = "047"
down_revision = "046"
branch_labels = None
depends_on = None


_MONEY_NUMERIC = sa.Numeric(10, 2)
_MONEY_FLOAT = sa.Float()


# Tables actually created by migrations. The grocery_basket model (with
# `weekly_grocery_baskets` and `basket_orders`) defines model classes
# but has no CREATE TABLE migration — they're dead code. Loop 13
# follow-up: either ship the missing migration or delete the models.
_TARGET_COLUMNS = [
    ("carts", "estimated_total", False, "0"),
    ("cart_items", "best_price", True, None),
    ("expense_entries", "amount", False, None),
    ("expense_settlements", "amount", False, None),
    ("monthly_budgets", "budget_amount", False, None),
    ("auto_approval_rules", "max_amount", False, "500"),
    ("families", "weekly_bulk_min_total", False, "800"),
]


def upgrade() -> None:
    for table, column, nullable, default in _TARGET_COLUMNS:
        # USING clause is required for Postgres to know how to coerce
        # the existing float values into numeric. `::numeric(10,2)` does
        # the right banker's-rounding-to-2dp thing.
        op.alter_column(
            table,
            column,
            type_=_MONEY_NUMERIC,
            existing_type=_MONEY_FLOAT,
            existing_nullable=nullable,
            postgresql_using=f"{column}::numeric(10,2)",
        )


def downgrade() -> None:
    for table, column, nullable, default in _TARGET_COLUMNS:
        op.alter_column(
            table,
            column,
            type_=_MONEY_FLOAT,
            existing_type=_MONEY_NUMERIC,
            existing_nullable=nullable,
            postgresql_using=f"{column}::double precision",
        )
