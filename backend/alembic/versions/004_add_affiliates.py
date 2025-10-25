"""Add affiliate system tables.

Revision ID: 004_add_affiliates
Revises: 003_add_trading_tables
Create Date: 2024-01-01 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "004_add_affiliates"
down_revision = "003_add_trading_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create affiliate system tables.

    Tables:
    - affiliates: User affiliate program participation
    - referrals: Signup tracking via referral links
    - commissions: Earned commissions from referred users
    - payouts: Commission payout requests
    """
    # Create affiliates table
    op.create_table(
        "affiliates",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("referral_token", sa.String(32), nullable=False),
        sa.Column("commission_tier", sa.Integer, nullable=False),
        sa.Column("earned_total", sa.Float, nullable=False, server_default="0"),
        sa.Column("paid_total", sa.Float, nullable=False, server_default="0"),
        sa.Column("pending_total", sa.Float, nullable=False, server_default="0"),
        sa.Column("status", sa.Integer, nullable=False),
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
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
        sa.UniqueConstraint("referral_token"),
    )
    op.create_index(
        "ix_affiliates_user_created", "affiliates", ["user_id", "created_at"]
    )
    op.create_index("ix_affiliates_status", "affiliates", ["status"])

    # Create referrals table
    op.create_table(
        "referrals",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("referrer_id", sa.String(36), nullable=False),
        sa.Column("referred_user_id", sa.String(36), nullable=False),
        sa.Column("status", sa.Integer, nullable=False),
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
        ),
        sa.ForeignKeyConstraint(["referrer_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["referred_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("referred_user_id"),
    )
    op.create_index(
        "ix_referrals_referrer_created", "referrals", ["referrer_id", "created_at"]
    )
    op.create_index("ix_referrals_status", "referrals", ["status"])

    # Create commissions table
    op.create_table(
        "commissions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("referrer_id", sa.String(36), nullable=False),
        sa.Column("referred_user_id", sa.String(36), nullable=False),
        sa.Column("trade_id", sa.String(36), nullable=False),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("tier", sa.Integer, nullable=False),
        sa.Column("status", sa.Integer, nullable=False),
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
        ),
        sa.ForeignKeyConstraint(["referrer_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["referred_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["trade_id"], ["trades.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_commissions_referrer_created", "commissions", ["referrer_id", "created_at"]
    )
    op.create_index("ix_commissions_status", "commissions", ["status"])

    # Create payouts table
    op.create_table(
        "payouts",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("referrer_id", sa.String(36), nullable=False),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("status", sa.Integer, nullable=False),
        sa.Column("bank_account", sa.String(255), nullable=True),
        sa.Column("reference", sa.String(64), nullable=True),
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
        ),
        sa.ForeignKeyConstraint(["referrer_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_payouts_referrer_created", "payouts", ["referrer_id", "created_at"]
    )
    op.create_index("ix_payouts_status", "payouts", ["status"])


def downgrade() -> None:
    """Drop affiliate system tables."""
    op.drop_index("ix_payouts_status", table_name="payouts")
    op.drop_index("ix_payouts_referrer_created", table_name="payouts")
    op.drop_table("payouts")

    op.drop_index("ix_commissions_status", table_name="commissions")
    op.drop_index("ix_commissions_referrer_created", table_name="commissions")
    op.drop_table("commissions")

    op.drop_index("ix_referrals_status", table_name="referrals")
    op.drop_index("ix_referrals_referrer_created", table_name="referrals")
    op.drop_table("referrals")

    op.drop_index("ix_affiliates_status", table_name="affiliates")
    op.drop_index("ix_affiliates_user_created", table_name="affiliates")
    op.drop_table("affiliates")
