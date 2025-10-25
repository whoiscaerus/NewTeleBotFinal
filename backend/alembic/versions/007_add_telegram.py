"""Add Telegram webhook tables.

Revision ID: 007_add_telegram
Revises: 006_add_execution_store
Create Date: 2024-01-01 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "007_add_telegram"
down_revision = "006_add_execution_store"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create Telegram webhook tables.

    Tables:
    - telegram_webhooks: Webhook event log
    - telegram_commands: Command registry
    """
    # Create telegram_webhooks table
    op.create_table(
        "telegram_webhooks",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=True),
        sa.Column("message_id", sa.Integer, nullable=False),
        sa.Column("chat_id", sa.Integer, nullable=False),
        sa.Column("command", sa.String(32), nullable=True),
        sa.Column("text", sa.Text, nullable=True),
        sa.Column("status", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_message", sa.String(255), nullable=True),
        sa.Column("handler_response_time_ms", sa.Integer, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_webhooks_user_created", "telegram_webhooks", ["user_id", "created_at"]
    )
    op.create_index(
        "ix_webhooks_message_id", "telegram_webhooks", ["message_id"], unique=True
    )
    op.create_index("ix_webhooks_command", "telegram_webhooks", ["command"])

    # Create telegram_commands table
    op.create_table(
        "telegram_commands",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("command", sa.String(32), nullable=False, unique=True),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("requires_auth", sa.Integer, nullable=False, server_default="1"),
        sa.Column("requires_premium", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_commands_command", "telegram_commands", ["command"])
    op.create_index("ix_commands_category", "telegram_commands", ["category"])


def downgrade() -> None:
    """Drop Telegram webhook tables."""
    op.drop_index("ix_commands_category", table_name="telegram_commands")
    op.drop_index("ix_commands_command", table_name="telegram_commands")
    op.drop_table("telegram_commands")

    op.drop_index("ix_webhooks_command", table_name="telegram_webhooks")
    op.drop_index("ix_webhooks_message_id", table_name="telegram_webhooks")
    op.drop_index("ix_webhooks_user_created", table_name="telegram_webhooks")
    op.drop_table("telegram_webhooks")
