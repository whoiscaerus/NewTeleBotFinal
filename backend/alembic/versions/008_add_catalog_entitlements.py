"""Add catalog and entitlements tables.

Revision ID: 008_add_catalog_entitlements
Revises: 007_add_telegram
Create Date: 2024-01-01 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "008_add_catalog_entitlements"
down_revision = "007_add_telegram"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create catalog and entitlements tables.

    Tables:
    - product_categories: Product categories
    - products: Products in catalog
    - product_tiers: Pricing tiers per product
    - entitlement_types: Feature/capability types
    - user_entitlements: User feature access
    """
    # Create product_categories table
    op.create_table(
        "product_categories",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("icon", sa.String(50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_categories_slug", "product_categories", ["slug"])
    op.create_index("ix_categories_name", "product_categories", ["name"])

    # Create products table
    op.create_table(
        "products",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("category_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("features", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["category_id"], ["product_categories.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_products_category", "products", ["category_id"])
    op.create_index("ix_products_slug", "products", ["slug"])
    op.create_index("ix_products_name", "products", ["name"])

    # Create product_tiers table
    op.create_table(
        "product_tiers",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("product_id", sa.String(36), nullable=False),
        sa.Column("tier_level", sa.Integer, nullable=False),
        sa.Column("tier_name", sa.String(50), nullable=False),
        sa.Column("base_price", sa.Float, nullable=False),
        sa.Column(
            "billing_period",
            sa.String(20),
            nullable=False,
            server_default="monthly",
        ),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_product_tiers_product", "product_tiers", ["product_id"])
    op.create_index("ix_product_tiers_level", "product_tiers", ["tier_level"])
    op.create_index(
        "ix_product_tier_unique",
        "product_tiers",
        ["product_id", "tier_level"],
        unique=True,
    )

    # Create entitlement_types table
    op.create_table(
        "entitlement_types",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(50), nullable=False, unique=True),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_entitlement_types_name", "entitlement_types", ["name"])

    # Create user_entitlements table
    op.create_table(
        "user_entitlements",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("entitlement_type_id", sa.String(36), nullable=False),
        sa.Column(
            "granted_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime, nullable=True),
        sa.Column("is_active", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["entitlement_type_id"], ["entitlement_types.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_entitlements_user", "user_entitlements", ["user_id"])
    op.create_index(
        "ix_user_entitlements_active",
        "user_entitlements",
        ["user_id", "is_active"],
    )
    op.create_index("ix_user_entitlements_expiry", "user_entitlements", ["expires_at"])


def downgrade() -> None:
    """Drop catalog and entitlements tables."""
    op.drop_index("ix_user_entitlements_expiry", table_name="user_entitlements")
    op.drop_index("ix_user_entitlements_active", table_name="user_entitlements")
    op.drop_index("ix_user_entitlements_user", table_name="user_entitlements")
    op.drop_table("user_entitlements")

    op.drop_index("ix_entitlement_types_name", table_name="entitlement_types")
    op.drop_table("entitlement_types")

    op.drop_index("ix_product_tier_unique", table_name="product_tiers")
    op.drop_index("ix_product_tiers_level", table_name="product_tiers")
    op.drop_index("ix_product_tiers_product", table_name="product_tiers")
    op.drop_table("product_tiers")

    op.drop_index("ix_products_name", table_name="products")
    op.drop_index("ix_products_slug", table_name="products")
    op.drop_index("ix_products_category", table_name="products")
    op.drop_table("products")

    op.drop_index("ix_categories_name", table_name="product_categories")
    op.drop_index("ix_categories_slug", table_name="product_categories")
    op.drop_table("product_categories")
