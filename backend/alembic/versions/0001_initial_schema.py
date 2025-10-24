"""Initial schema: users and audit_logs tables.

Revision ID: 0001
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create initial tables: users, audit_logs."""
    
    # Create users table
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column(
            "role",
            sa.Enum("owner", "admin", "user", name="userrole"),
            nullable=False,
            server_default="user",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_role", "users", ["role"])

    # Create audit_logs table
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column(
            "timestamp",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("actor_id", sa.String(36), nullable=True),
        sa.Column("actor_role", sa.String(20), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("target", sa.String(50), nullable=False),
        sa.Column("target_id", sa.String(36), nullable=True),
        sa.Column("meta", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="success"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_actor_time", "audit_logs", ["actor_id", "timestamp"])
    op.create_index("ix_audit_action_time", "audit_logs", ["action", "timestamp"])
    op.create_index(
        "ix_audit_target_time", "audit_logs", ["target", "target_id", "timestamp"]
    )
    op.create_index("ix_audit_status_time", "audit_logs", ["status", "timestamp"])
    op.create_index("ix_audit_timestamp", "audit_logs", ["timestamp"])
    op.create_index("ix_audit_actor_id", "audit_logs", ["actor_id"])
    op.create_index("ix_audit_action", "audit_logs", ["action"])
    op.create_index("ix_audit_target", "audit_logs", ["target"])
    op.create_index("ix_audit_status", "audit_logs", ["status"])


def downgrade() -> None:
    """Drop initial tables."""
    op.drop_table("audit_logs")
    op.drop_table("users")
