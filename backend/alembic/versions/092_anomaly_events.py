"""PR-092: Add anomaly_events table for fraud detection.

Revision ID: 092_anomaly_events
Revises: 091_feature_flags
Create Date: 2024-11-10 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "092_anomaly_events"
down_revision = "091_feature_flags"
branch_labels = None
depends_on = None


def upgrade():
    """Create anomaly_events table for fraud detection."""
    op.create_table(
        "anomaly_events",
        # Primary Key
        sa.Column("event_id", sa.String(length=36), nullable=False),
        # Foreign Keys
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("trade_id", sa.String(length=36), nullable=True),
        # Anomaly Details
        sa.Column("anomaly_type", sa.String(length=50), nullable=False),
        sa.Column(
            "severity", sa.String(length=20), nullable=False, server_default="low"
        ),
        sa.Column("score", sa.Numeric(precision=5, scale=4), nullable=False),
        # Metadata (JSON stored as TEXT)
        sa.Column("details", sa.Text(), nullable=False),
        # Detection Timestamp
        sa.Column(
            "detected_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        # Review Tracking
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("reviewed_by", sa.String(length=36), nullable=True),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="open"
        ),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        # Timestamps
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        # Constraints
        sa.PrimaryKeyConstraint("event_id"),
    )

    # Indexes for common queries
    op.create_index(
        "ix_anomaly_events_user_id",
        "anomaly_events",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_anomaly_events_trade_id",
        "anomaly_events",
        ["trade_id"],
        unique=False,
    )
    op.create_index(
        "ix_anomaly_events_anomaly_type",
        "anomaly_events",
        ["anomaly_type"],
        unique=False,
    )
    op.create_index(
        "ix_anomaly_events_detected_at",
        "anomaly_events",
        ["detected_at"],
        unique=False,
    )

    # Composite indexes for filtering
    op.create_index(
        "ix_anomaly_events_type_detected",
        "anomaly_events",
        ["anomaly_type", "detected_at"],
        unique=False,
    )
    op.create_index(
        "ix_anomaly_events_severity_status",
        "anomaly_events",
        ["severity", "status"],
        unique=False,
    )
    op.create_index(
        "ix_anomaly_events_user_detected",
        "anomaly_events",
        ["user_id", "detected_at"],
        unique=False,
    )

    print("✅ PR-092: Created anomaly_events table with indexes")


def downgrade():
    """Drop anomaly_events table."""
    op.drop_index("ix_anomaly_events_user_detected", table_name="anomaly_events")
    op.drop_index("ix_anomaly_events_severity_status", table_name="anomaly_events")
    op.drop_index("ix_anomaly_events_type_detected", table_name="anomaly_events")
    op.drop_index("ix_anomaly_events_detected_at", table_name="anomaly_events")
    op.drop_index("ix_anomaly_events_anomaly_type", table_name="anomaly_events")
    op.drop_index("ix_anomaly_events_trade_id", table_name="anomaly_events")
    op.drop_index("ix_anomaly_events_user_id", table_name="anomaly_events")
    op.drop_table("anomaly_events")

    print("✅ PR-092: Dropped anomaly_events table")
