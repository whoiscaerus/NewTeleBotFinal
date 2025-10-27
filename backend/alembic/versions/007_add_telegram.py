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
    """Create Telegram tables.

    Tables:
    - telegram_webhooks: Webhook event log
    - telegram_commands: Command registry
    - telegram_users: User accounts with RBAC
    - telegram_guides: Educational content
    - telegram_broadcasts: Marketing broadcasts
    - telegram_user_guide_collections: User's saved guides
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

    # Create telegram_users table
    op.create_table(
        "telegram_users",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("telegram_id", sa.String(36), nullable=True, unique=True),
        sa.Column("telegram_username", sa.String(32), nullable=True),
        sa.Column("telegram_first_name", sa.String(64), nullable=True),
        sa.Column("telegram_last_name", sa.String(64), nullable=True),
        sa.Column("role", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("preferences", sa.Text, nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_telegram_id", "telegram_users", ["telegram_id"])
    op.create_index("ix_users_username", "telegram_users", ["telegram_username"])
    op.create_index("ix_users_role", "telegram_users", ["role"])
    op.create_index("ix_users_created", "telegram_users", ["created_at"])

    # Create telegram_guides table
    op.create_table(
        "telegram_guides",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("content_url", sa.String(512), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("tags", sa.Text, nullable=True),
        sa.Column("difficulty_level", sa.Integer, nullable=False, server_default="0"),
        sa.Column("views_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="1"),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_guides_title", "telegram_guides", ["title"])
    op.create_index("ix_guides_category", "telegram_guides", ["category"])
    op.create_index("ix_guides_difficulty", "telegram_guides", ["difficulty_level"])
    op.create_index("ix_guides_created", "telegram_guides", ["created_at"])

    # Create telegram_broadcasts table
    op.create_table(
        "telegram_broadcasts",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("message_text", sa.Text, nullable=False),
        sa.Column("message_type", sa.String(32), nullable=False, server_default="text"),
        sa.Column(
            "target_audience", sa.String(32), nullable=False, server_default="all"
        ),
        sa.Column("status", sa.Integer, nullable=False, server_default="0"),
        sa.Column("scheduled_at", sa.DateTime, nullable=True),
        sa.Column("sent_at", sa.DateTime, nullable=True),
        sa.Column("recipients_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_by_id", sa.String(36), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_broadcasts_status", "telegram_broadcasts", ["status"])
    op.create_index("ix_broadcasts_scheduled", "telegram_broadcasts", ["scheduled_at"])
    op.create_index("ix_broadcasts_created", "telegram_broadcasts", ["created_at"])

    # Create telegram_user_guide_collections table
    op.create_table(
        "telegram_user_guide_collections",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("guide_id", sa.String(36), nullable=False),
        sa.Column("is_read", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("times_viewed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_viewed_at", sa.DateTime, nullable=True),
        sa.Column(
            "saved_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["telegram_users.id"]),
        sa.ForeignKeyConstraint(["guide_id"], ["telegram_guides.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_collection_user", "telegram_user_guide_collections", ["user_id"]
    )
    op.create_index(
        "ix_collection_guide", "telegram_user_guide_collections", ["guide_id"]
    )
    op.create_index(
        "ix_collection_user_guide",
        "telegram_user_guide_collections",
        ["user_id", "guide_id"],
        unique=True,
    )
    op.create_index(
        "ix_collection_saved", "telegram_user_guide_collections", ["saved_at"]
    )


def downgrade() -> None:
    """Drop Telegram tables."""
    op.drop_index("ix_collection_saved", table_name="telegram_user_guide_collections")
    op.drop_index(
        "ix_collection_user_guide", table_name="telegram_user_guide_collections"
    )
    op.drop_index("ix_collection_guide", table_name="telegram_user_guide_collections")
    op.drop_index("ix_collection_user", table_name="telegram_user_guide_collections")
    op.drop_table("telegram_user_guide_collections")

    op.drop_index("ix_broadcasts_created", table_name="telegram_broadcasts")
    op.drop_index("ix_broadcasts_scheduled", table_name="telegram_broadcasts")
    op.drop_index("ix_broadcasts_status", table_name="telegram_broadcasts")
    op.drop_table("telegram_broadcasts")

    op.drop_index("ix_guides_created", table_name="telegram_guides")
    op.drop_index("ix_guides_difficulty", table_name="telegram_guides")
    op.drop_index("ix_guides_category", table_name="telegram_guides")
    op.drop_table("telegram_guides")

    op.drop_index("ix_users_created", table_name="telegram_users")
    op.drop_index("ix_users_role", table_name="telegram_users")
    op.drop_index("ix_users_telegram_id", table_name="telegram_users")
    op.drop_table("telegram_users")

    op.drop_index("ix_commands_category", table_name="telegram_commands")
    op.drop_index("ix_commands_command", table_name="telegram_commands")
    op.drop_table("telegram_commands")

    op.drop_index("ix_webhooks_command", table_name="telegram_webhooks")
    op.drop_index("ix_webhooks_message_id", table_name="telegram_webhooks")
    op.drop_index("ix_webhooks_user_created", table_name="telegram_webhooks")
    op.drop_table("telegram_webhooks")
