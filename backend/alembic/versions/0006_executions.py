"""Alembic migration: Create executions table for PR-024a."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision = "0006_executions"
down_revision = "0005_clients_devices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create executions table with indexes and constraints."""
    op.create_table(
        "executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approval_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "placed",
                "failed",
                "cancelled",
                "unknown",
                name="executionstatus",
            ),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("broker_ticket", sa.String(128), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["approval_id"],
            ["approvals.id"],
            name="fk_executions_approval",
        ),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["devices.id"],
            name="fk_executions_device",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Indexes
    op.create_index(
        "ix_executions_approval_id",
        "executions",
        ["approval_id"],
        unique=False,
    )
    op.create_index(
        "ix_executions_device_id",
        "executions",
        ["device_id"],
        unique=False,
    )
    op.create_index(
        "ix_executions_status",
        "executions",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_executions_broker_ticket",
        "executions",
        ["broker_ticket"],
        unique=False,
    )
    op.create_index(
        "ix_executions_created_at",
        "executions",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_executions_approval_device",
        "executions",
        ["approval_id", "device_id"],
        unique=False,
    )
    op.create_index(
        "ix_executions_status_created",
        "executions",
        ["status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop executions table."""
    op.drop_table("executions")
