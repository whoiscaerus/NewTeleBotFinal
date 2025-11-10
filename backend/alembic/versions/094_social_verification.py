"""PR-094: Add verification_edges table for social verification graph.

Revision ID: 094_social_verification
Revises: 092_anomaly_events
Create Date: 2024-11-10 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "094_social_verification"
down_revision = "092_anomaly_events"
branch_labels = None
depends_on = None


def upgrade():
    """Create verification_edges table for social verification graph."""
    op.create_table(
        "verification_edges",
        # Primary Key
        sa.Column("id", sa.String(length=36), nullable=False),
        # Foreign Keys
        sa.Column("verifier_id", sa.String(length=36), nullable=False),
        sa.Column("verified_id", sa.String(length=36), nullable=False),
        # Verification Details
        sa.Column("weight", sa.Float, nullable=False, server_default="1.0"),
        sa.Column(
            "created_at", sa.DateTime, nullable=False, server_default=sa.func.now()
        ),
        # Anti-Sybil Metadata
        sa.Column("ip_address", sa.String(length=45), nullable=True),  # IPv6 support
        sa.Column("device_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("notes", sa.String(length=500), nullable=True),
        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["verifier_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["verified_id"], ["users.id"], ondelete="CASCADE"),
    )

    # Indexes for social graph queries
    op.create_index(
        "ix_verification_unique_pair",
        "verification_edges",
        ["verifier_id", "verified_id"],
        unique=True,
    )
    op.create_index(
        "ix_verification_verifier_created",
        "verification_edges",
        ["verifier_id", "created_at"],
    )
    op.create_index(
        "ix_verification_verified_created",
        "verification_edges",
        ["verified_id", "created_at"],
    )

    # Indexes for anti-sybil rate limiting
    op.create_index(
        "ix_verification_ip_created",
        "verification_edges",
        ["ip_address", "created_at"],
    )
    op.create_index(
        "ix_verification_device_created",
        "verification_edges",
        ["device_fingerprint", "created_at"],
    )


def downgrade():
    """Drop verification_edges table."""
    op.drop_index("ix_verification_device_created", table_name="verification_edges")
    op.drop_index("ix_verification_ip_created", table_name="verification_edges")
    op.drop_index("ix_verification_verified_created", table_name="verification_edges")
    op.drop_index("ix_verification_verifier_created", table_name="verification_edges")
    op.drop_index("ix_verification_unique_pair", table_name="verification_edges")
    op.drop_table("verification_edges")
