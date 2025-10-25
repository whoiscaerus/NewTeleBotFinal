"""Add orders tables.

Revision ID: 009_add_orders
Revises: 008_add_catalog_entitlements
Create Date: 2024-01-01 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "009_add_orders"
down_revision = "008_add_catalog_entitlements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create orders tables.

    Tables:
    - orders: Order records
    - order_items: Items in each order
    """
    # Create orders table
    op.create_table(
        "orders",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("product_tier_id", sa.String(36), nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False, server_default="1"),
        sa.Column("base_price", sa.Float, nullable=False),
        sa.Column("final_price", sa.Float, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="GBP"),
        sa.Column(
            "status", sa.Integer, nullable=False, server_default="0"
        ),  # 0=pending, 1=completed, 2=failed, 3=cancelled
        sa.Column("payment_method", sa.String(20), nullable=True),
        sa.Column("transaction_id", sa.String(255), nullable=True),
        sa.Column("notes", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_orders_user", "orders", ["user_id"])
    op.create_index("ix_orders_user_created", "orders", ["user_id", "created_at"])
    op.create_index("ix_orders_status", "orders", ["status"])
    op.create_index("ix_orders_transaction_id", "orders", ["transaction_id"])

    # Create order_items table
    op.create_table(
        "order_items",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("order_id", sa.String(36), nullable=False),
        sa.Column("product_tier_id", sa.String(36), nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False, server_default="1"),
        sa.Column("unit_price", sa.Float, nullable=False),
        sa.Column("total_price", sa.Float, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_order_items_order", "order_items", ["order_id"])


def downgrade() -> None:
    """Drop orders tables."""
    op.drop_index("ix_order_items_order", table_name="order_items")
    op.drop_table("order_items")

    op.drop_index("ix_orders_transaction_id", table_name="orders")
    op.drop_index("ix_orders_status", table_name="orders")
    op.drop_index("ix_orders_user_created", table_name="orders")
    op.drop_index("ix_orders_user", table_name="orders")
    op.drop_table("orders")
