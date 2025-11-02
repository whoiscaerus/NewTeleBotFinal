"""
PR-046: Copy-Trading Risk & Compliance Controls - Database Migration

Adds PR-046 features:
- Risk parameters: max_leverage, max_per_trade_risk_percent, total_exposure_percent, daily_stop_percent
- Pause mechanism: is_paused, pause_reason, paused_at
- Breach tracking: last_breach_at, last_breach_reason
- Disclosure versioning: disclosures table, user_consents table
- Audit trail: immutable consent logs with IP and user agent

Revision ID: 012_pr_046_risk_compliance
Revises: 011_add_distribution
Create Date: 2025-10-31
"""

import sqlalchemy as sa
from alembic import op

# Revision identifiers
revision = "012_pr_046_risk_compliance"
down_revision = "011_add_distribution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply PR-046 migrations."""

    # Step 1: Add PR-046 columns to copy_trade_settings
    op.add_column(
        "copy_trade_settings",
        sa.Column(
            "max_leverage",
            sa.Float(),
            nullable=False,
            server_default="5.0",
            comment="Max leverage per trade (1x-10x)",
        ),
    )
    op.add_column(
        "copy_trade_settings",
        sa.Column(
            "max_per_trade_risk_percent",
            sa.Float(),
            nullable=False,
            server_default="2.0",
            comment="Max risk per trade as % of account",
        ),
    )
    op.add_column(
        "copy_trade_settings",
        sa.Column(
            "total_exposure_percent",
            sa.Float(),
            nullable=False,
            server_default="50.0",
            comment="Max total exposure % across all positions",
        ),
    )
    op.add_column(
        "copy_trade_settings",
        sa.Column(
            "daily_stop_percent",
            sa.Float(),
            nullable=False,
            server_default="10.0",
            comment="Max daily loss % before pause",
        ),
    )
    op.add_column(
        "copy_trade_settings",
        sa.Column(
            "is_paused",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="Paused due to breach",
        ),
    )
    op.add_column(
        "copy_trade_settings",
        sa.Column(
            "pause_reason",
            sa.String(500),
            nullable=True,
            comment="Reason for pause (breach type)",
        ),
    )
    op.add_column(
        "copy_trade_settings",
        sa.Column(
            "paused_at",
            sa.DateTime(),
            nullable=True,
            comment="When pause was triggered",
        ),
    )
    op.add_column(
        "copy_trade_settings",
        sa.Column(
            "last_breach_at",
            sa.DateTime(),
            nullable=True,
            comment="Last time risk breach detected",
        ),
    )
    op.add_column(
        "copy_trade_settings",
        sa.Column(
            "last_breach_reason",
            sa.String(500),
            nullable=True,
            comment="Type of breach",
        ),
    )

    # Step 2: Add index for pause queries
    op.create_index(
        "ix_copy_paused_user",
        "copy_trade_settings",
        ["is_paused", "user_id"],
        unique=False,
    )

    # Step 3: Create disclosures table
    op.create_table(
        "disclosures",
        sa.Column(
            "id",
            sa.String(36),
            nullable=False,
            primary_key=True,
        ),
        sa.Column(
            "version",
            sa.String(50),
            nullable=False,
            unique=True,
            comment="Version string (1.0, 1.1, 2.0)",
        ),
        sa.Column(
            "title", sa.String(500), nullable=False, comment="Human-readable title"
        ),
        sa.Column("content", sa.Text(), nullable=False, comment="Full disclosure text"),
        sa.Column(
            "effective_date",
            sa.DateTime(),
            nullable=False,
            comment="When disclosure becomes active",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default="true",
            comment="Current version",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_disclosure_version", "disclosures", ["version"], unique=False)
    op.create_index("ix_disclosure_active", "disclosures", ["is_active"], unique=False)

    # Step 4: Create user_consents table (immutable audit trail)
    op.create_table(
        "user_consents",
        sa.Column(
            "id",
            sa.String(36),
            nullable=False,
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "disclosure_version",
            sa.String(50),
            nullable=False,
            comment="Version accepted",
        ),
        sa.Column(
            "accepted_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            comment="When accepted",
        ),
        sa.Column("ip_address", sa.String(45), nullable=True, comment="IPv4 or IPv6"),
        sa.Column(
            "user_agent", sa.String(500), nullable=True, comment="Browser/client info"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_user_consent_user_version",
        "user_consents",
        ["user_id", "disclosure_version"],
        unique=False,
    )
    op.create_index(
        "ix_user_consent_user_date",
        "user_consents",
        ["user_id", "accepted_at"],
        unique=False,
    )


def downgrade() -> None:
    """Revert PR-046 migrations."""

    # Step 1: Drop user_consents table
    op.drop_index("ix_user_consent_user_date", "user_consents")
    op.drop_index("ix_user_consent_user_version", "user_consents")
    op.drop_table("user_consents")

    # Step 2: Drop disclosures table
    op.drop_index("ix_disclosure_active", "disclosures")
    op.drop_index("ix_disclosure_version", "disclosures")
    op.drop_table("disclosures")

    # Step 3: Drop pause index
    op.drop_index("ix_copy_paused_user", "copy_trade_settings")

    # Step 4: Remove PR-046 columns from copy_trade_settings
    op.drop_column("copy_trade_settings", "last_breach_reason")
    op.drop_column("copy_trade_settings", "last_breach_at")
    op.drop_column("copy_trade_settings", "paused_at")
    op.drop_column("copy_trade_settings", "pause_reason")
    op.drop_column("copy_trade_settings", "is_paused")
    op.drop_column("copy_trade_settings", "daily_stop_percent")
    op.drop_column("copy_trade_settings", "total_exposure_percent")
    op.drop_column("copy_trade_settings", "max_per_trade_risk_percent")
    op.drop_column("copy_trade_settings", "max_leverage")
