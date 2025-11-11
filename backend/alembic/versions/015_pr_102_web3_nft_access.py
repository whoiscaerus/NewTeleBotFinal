"""PR-102: Add web3 wallet links and NFT access tables

Revision ID: 015_pr_102_web3_nft_access
Revises: 014_pr_101_reports
Create Date: 2025-11-11 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import JSON

# revision identifiers, used by Alembic.
revision = "015_pr_102_web3_nft_access"
down_revision = "014_pr_101_reports"  # Update this to match latest migration
branch_labels = None
depends_on = None


def upgrade():
    """Create web3 wallet links and NFT access tables."""

    # Create wallet_links table
    op.create_table(
        "wallet_links",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("wallet_address", sa.String(42), nullable=False, unique=True),
        sa.Column("chain_id", sa.Integer(), nullable=False, default=1),
        sa.Column("signature", sa.String(132), nullable=True),
        sa.Column("message", sa.String(255), nullable=True),
        sa.Column("verified_at", sa.DateTime(), nullable=False),
        sa.Column("is_active", sa.Integer(), nullable=False, default=1),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
    )

    # Create indexes for wallet_links
    op.create_index("ix_wallet_links_user", "wallet_links", ["user_id"])
    op.create_index("ix_wallet_links_address", "wallet_links", ["wallet_address"])
    op.create_index("ix_wallet_links_active", "wallet_links", ["is_active"])

    # Create nft_access table
    op.create_table(
        "nft_access",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "wallet_address",
            sa.String(42),
            sa.ForeignKey("wallet_links.wallet_address", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entitlement_key", sa.String(50), nullable=False),
        sa.Column("token_id", sa.String(100), nullable=True),
        sa.Column("contract_address", sa.String(42), nullable=True),
        sa.Column("chain_id", sa.Integer(), nullable=False, default=1),
        sa.Column("is_active", sa.Integer(), nullable=False, default=1),
        sa.Column("minted_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("revoke_reason", sa.String(255), nullable=True),
        sa.Column("meta", JSON, nullable=True),
    )

    # Create indexes for nft_access
    op.create_index("ix_nft_access_user", "nft_access", ["user_id"])
    op.create_index("ix_nft_access_wallet", "nft_access", ["wallet_address"])
    op.create_index("ix_nft_access_entitlement", "nft_access", ["entitlement_key"])
    op.create_index("ix_nft_access_active", "nft_access", ["is_active", "expires_at"])


def downgrade():
    """Drop web3 tables."""

    # Drop indexes first
    op.drop_index("ix_nft_access_active", table_name="nft_access")
    op.drop_index("ix_nft_access_entitlement", table_name="nft_access")
    op.drop_index("ix_nft_access_wallet", table_name="nft_access")
    op.drop_index("ix_nft_access_user", table_name="nft_access")

    op.drop_index("ix_wallet_links_active", table_name="wallet_links")
    op.drop_index("ix_wallet_links_address", table_name="wallet_links")
    op.drop_index("ix_wallet_links_user", table_name="wallet_links")

    # Drop tables
    op.drop_table("nft_access")
    op.drop_table("wallet_links")
