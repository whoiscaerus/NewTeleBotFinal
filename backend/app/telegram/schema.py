"""Pydantic schemas for Telegram webhook validation."""

from typing import Optional

from pydantic import BaseModel, Field


class TelegramUser(BaseModel):
    """Telegram user information."""

    id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None


class TelegramChat(BaseModel):
    """Telegram chat information."""

    id: int
    type: str  # 'private', 'group', 'channel', etc
    title: str | None = None
    username: str | None = None


class TelegramMessage(BaseModel):
    """Telegram message from user."""

    message_id: int
    date: int
    chat: TelegramChat
    from_user: TelegramUser = Field(alias="from")
    text: str | None = None
    forward_from_chat: Optional["TelegramChat"] = None
    reply_to_message: Optional["TelegramMessage"] = None

    class Config:
        populate_by_name = True


class TelegramCallback(BaseModel):
    """Telegram callback query (button click)."""

    id: str
    from_user: TelegramUser = Field(alias="from")
    chat_instance: str
    message: TelegramMessage | None = None
    data: str | None = None  # Button callback data

    class Config:
        populate_by_name = True


class TelegramUpdate(BaseModel):
    """Telegram webhook update."""

    update_id: int
    message: TelegramMessage | None = None
    callback_query: TelegramCallback | None = None
    edited_message: TelegramMessage | None = None


class WebhookEventOut(BaseModel):
    """Response schema for webhook event."""

    id: str
    user_id: str | None = None
    message_id: int
    command: str | None = None
    status: int
    created_at: str


TelegramUpdate.model_rebuild()
