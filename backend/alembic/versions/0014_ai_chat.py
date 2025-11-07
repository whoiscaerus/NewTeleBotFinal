"""Create AI chat tables.

Revision ID: 0014_ai_chat
Revises: 0013_xxx
Create Date: 2025-01-15 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "0014_ai_chat"
down_revision = "0013_xxx"  # Update to actual previous revision
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create AI chat tables with indexes."""

    # Create chat sessions table
    op.create_table(
        "ai_chat_sessions",
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("escalated", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("escalation_reason", sa.Text, nullable=True),
        sa.Column("channel", sa.String(20), nullable=False, server_default="web"),
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
            onupdate=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    op.create_index(
        "ix_ai_chat_sessions_user",
        "ai_chat_sessions",
        ["user_id", "created_at"],
        mysql_length={"user_id": 36},
    )
    op.create_index(
        "ix_ai_chat_sessions_escalated",
        "ai_chat_sessions",
        ["escalated"],
    )

    # Create chat messages table
    op.create_table(
        "ai_chat_messages",
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("role", sa.Integer, nullable=False),  # 0=user, 1=assistant, 2=system
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("citations", sa.JSON, nullable=True),
        sa.Column("blocked_by_policy", sa.String(100), nullable=True),
        sa.Column("confidence_score", sa.Float, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["ai_chat_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    op.create_index(
        "ix_ai_chat_messages_session",
        "ai_chat_messages",
        ["session_id", "created_at"],
        mysql_length={"session_id": 36},
    )
    op.create_index(
        "ix_ai_chat_messages_user",
        "ai_chat_messages",
        ["user_id", "created_at"],
        mysql_length={"user_id": 36},
    )
    op.create_index(
        "ix_ai_chat_messages_role",
        "ai_chat_messages",
        ["session_id", "role"],
        mysql_length={"session_id": 36},
    )

    # Create KB embeddings table (RAG index)
    op.create_table(
        "ai_kb_embeddings",
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("article_id", sa.String(36), nullable=False),
        sa.Column("embedding", sa.JSON, nullable=False),
        sa.Column(
            "model", sa.String(50), nullable=False, server_default="mock-embed-v1"
        ),
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
            onupdate=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["kb_articles.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("article_id", name="uq_ai_kb_embeddings_article_id"),
    )

    op.create_index(
        "ix_ai_kb_embeddings_created",
        "ai_kb_embeddings",
        ["created_at"],
    )
    op.create_index(
        "ix_ai_kb_embeddings_model",
        "ai_kb_embeddings",
        ["model"],
    )


def downgrade() -> None:
    """Drop AI chat tables."""
    op.drop_index("ix_ai_kb_embeddings_model", table_name="ai_kb_embeddings")
    op.drop_index("ix_ai_kb_embeddings_created", table_name="ai_kb_embeddings")
    op.drop_table("ai_kb_embeddings")

    op.drop_index("ix_ai_chat_messages_role", table_name="ai_chat_messages")
    op.drop_index("ix_ai_chat_messages_user", table_name="ai_chat_messages")
    op.drop_index("ix_ai_chat_messages_session", table_name="ai_chat_messages")
    op.drop_table("ai_chat_messages")

    op.drop_index("ix_ai_chat_sessions_escalated", table_name="ai_chat_sessions")
    op.drop_index("ix_ai_chat_sessions_user", table_name="ai_chat_sessions")
    op.drop_table("ai_chat_sessions")
