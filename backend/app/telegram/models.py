"""Telegram webhook models for event tracking and command registry."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Index, Integer, String, Text

from backend.app.core.db import Base


class TelegramWebhook(Base):
    """Telegram webhook event log.

    Tracks all incoming Telegram webhook events for audit and debugging.
    Uses message_id as unique key for idempotency.
    """

    __tablename__ = "telegram_webhooks"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), nullable=True, index=True)
    message_id = Column(Integer, nullable=False)
    chat_id = Column(Integer, nullable=False, index=True)
    command = Column(String(32), nullable=True, index=True)
    text = Column(Text, nullable=True)
    status = Column(
        Integer, nullable=False, default=0
    )  # 0=new, 1=processing, 2=success, 3=error
    error_message = Column(String(255), nullable=True)
    handler_response_time_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_webhooks_user_created", "user_id", "created_at"),
        Index("ix_webhooks_message_id", "message_id", unique=True),
        Index("ix_webhooks_command", "command"),
    )

    def __repr__(self) -> str:
        return f"<TelegramWebhook {self.id}: {self.command} from {self.user_id}>"


class TelegramCommand(Base):
    """Telegram command registry and metadata.

    Stores available commands, categories, and permissions.
    """

    __tablename__ = "telegram_commands"

    id = Column(String(36), primary_key=True)
    command = Column(String(32), nullable=False, unique=True, index=True)
    category = Column(
        String(32), nullable=False
    )  # 'billing', 'signals', 'help', 'affiliate'
    description = Column(String(255), nullable=True)
    requires_auth = Column(Integer, nullable=False, default=1)
    requires_premium = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (Index("ix_commands_category", "category"),)

    def __repr__(self) -> str:
        return f"<TelegramCommand /{self.command}: {self.description}>"
