"""Drop residue tables from the retired Instacook + rides + multi-platform commerce.

Three large feature domains were retired:

  - Instacook marketplace (pool cooks, on-demand bookings, Gold membership,
    household credits, savings ledger, interest waitlist). Historical
    migrations 019, 020, 032 (partial), 034, 035, 036 were deleted from
    history.
  - Rides (cab/auto booking flow). Historical migration 003 was deleted
    from history.
  - Multi-platform commerce (Urban Company, Zepto, Blinkit, BigBasket, DMart,
    JioMart, Flipkart Minutes, Amazon Fresh) with `platform_sessions` and
    `service_bookings` tables. Historical migrations 006, 009, 013 were
    deleted, and 026's UC-removal commands were removed.

This migration cleans up any database that was partially upgraded prior to
the retirements, by dropping the orphan tables + types + columns if they
exist. On a fresh DB the IF EXISTS clauses make this a no-op.

Revision ID: 040
Revises: 039
"""

from alembic import op


revision = "040"
down_revision = "039"
branch_labels = None
depends_on = None


_TABLES_TO_DROP = [
    # Instacook marketplace
    "instacook_cook_household_history",
    "instacook_booking_feedback",
    "instacook_bookings",
    "instacook_cook_availability",
    "instacook_pool_cooks",
    "instacook_micromarkets",
    "instacook_interests",
    # Membership + monetisation tables that hung off Instacook
    "household_credits",
    "savings_events",
    "memberships",
    # Rides domain
    "ride_requests",
    "saved_locations",
    "pre_authorized_routes",
    # Multi-platform commerce
    "service_bookings",
    "platform_sessions",
]


_TYPES_TO_DROP = [
    "ridestatus",
    "rideurgency",
]


# Per-children plaintext platform tokens that may linger if the DB was
# partially upgraded before migration 009 ran in the original chain.
_COLUMNS_TO_DROP: list[tuple[str, str]] = [
    ("children", "swiggy_auth_token"),
    ("children", "zepto_auth_token"),
]


def upgrade() -> None:
    # CASCADE drops dependent indexes and constraints in one shot.
    for table in _TABLES_TO_DROP:
        op.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
    # Postgres enums for rides — must be dropped after the tables that used
    # them are gone (CASCADE on the table-drop above takes care of column
    # references, but the type itself persists until explicitly dropped).
    for type_name in _TYPES_TO_DROP:
        op.execute(f'DROP TYPE IF EXISTS "{type_name}" CASCADE')
    # Drop residual plaintext token columns from `children` that may still
    # exist on partially-migrated databases.
    for table, col in _COLUMNS_TO_DROP:
        op.execute(f'ALTER TABLE IF EXISTS "{table}" DROP COLUMN IF EXISTS "{col}"')


def downgrade() -> None:
    # We deliberately do NOT recreate the dropped tables/types. Instacook +
    # rides are gone — recreating their empty schemas would just add confusion.
    # To restore either feature, restore the deleted migrations from git
    # history and start from there.
    pass
