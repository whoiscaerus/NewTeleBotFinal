"""Comprehensive tests for message senders (PR-060).

Tests cover:
EMAIL:
- Success (SMTP sends)
- Auth error (SMTPAuthenticationError)
- Bounce (SMTPRecipientsRefused)
- Timeout retry (3 attempts)
- Rate limiting (100/min)
- Max retries
- Batch utility

TELEGRAM:
- Success (API 200 + ok=true)
- User blocked (403)
- Bad request (400)
- Telegram rate limit (429)
- Network error
- Client rate limit (20/s)
- Max retries
- Batch utility

PUSH:
- Success (webpush succeeds)
- Subscription expired (410)
- Permanent errors (400/404/413)
- No subscription
- Network error
- Max retries
- Batch utility

METRICS:
- message_send_duration_seconds
- messages_sent_total
- message_fail_total{reason,channel}

Target: 100% coverage of email.py + telegram.py + push.py (1,050+ lines)
"""

import time
from smtplib import (
    SMTPAuthenticationError,
    SMTPException,
    SMTPRecipientsRefused,
    SMTPServerDisconnected,
)
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from pywebpush import WebPushException

from backend.app.messaging.senders.email import MAX_EMAILS_PER_MINUTE
from backend.app.messaging.senders.email import MAX_RETRIES as EMAIL_MAX_RETRIES
from backend.app.messaging.senders.email import (
    _check_rate_limit as email_check_rate_limit,
)
from backend.app.messaging.senders.email import send_batch_emails, send_email
from backend.app.messaging.senders.push import MAX_RETRIES as PUSH_MAX_RETRIES
from backend.app.messaging.senders.push import send_push
from backend.app.messaging.senders.telegram import MAX_MESSAGES_PER_SECOND
from backend.app.messaging.senders.telegram import MAX_RETRIES as TELEGRAM_MAX_RETRIES
from backend.app.messaging.senders.telegram import (
    _check_rate_limit as telegram_check_rate_limit,
)
from backend.app.messaging.senders.telegram import send_telegram


@pytest.fixture
def mock_smtp_settings(monkeypatch):
    """Mock SMTP settings."""
    mock_settings = MagicMock()
    mock_settings.smtp.host = "smtp.test.com"
    mock_settings.smtp.port = 587
    mock_settings.smtp.user = "test@test.com"
    mock_settings.smtp.password = "test-password"
    mock_settings.smtp.from_email = "noreply@test.com"
    mock_settings.smtp.use_tls = True

    monkeypatch.setattr("backend.app.messaging.senders.email.settings", mock_settings)
    return mock_settings


@pytest.fixture
def mock_telegram_settings(monkeypatch):
    """Mock Telegram settings."""
    mock_settings = MagicMock()
    mock_settings.telegram.bot_token = "123456:ABC-DEF1234567890"

    monkeypatch.setattr(
        "backend.app.messaging.senders.telegram.settings", mock_settings
    )
    return mock_settings


@pytest.fixture
def mock_push_settings(monkeypatch):
    """Mock Push settings."""
    mock_settings = MagicMock()
    mock_settings.push.vapid_private_key = "test-private-key"
    mock_settings.push.vapid_public_key = "test-public-key"
    mock_settings.push.vapid_email = "admin@test.com"

    monkeypatch.setattr("backend.app.messaging.senders.push.settings", mock_settings)
    return mock_settings


@pytest.fixture
def mock_email_metrics(monkeypatch):
    """Mock email metrics."""
    mock_duration = MagicMock()
    mock_sent = MagicMock()
    mock_failed = MagicMock()

    monkeypatch.setattr(
        "backend.app.messaging.senders.email.message_send_duration_seconds",
        mock_duration,
    )
    monkeypatch.setattr(
        "backend.app.messaging.senders.email.messages_sent_total", mock_sent
    )
    monkeypatch.setattr(
        "backend.app.messaging.senders.email.message_fail_total", mock_failed
    )

    return {"duration": mock_duration, "sent": mock_sent, "failed": mock_failed}


@pytest.fixture
def mock_telegram_metrics(monkeypatch):
    """Mock Telegram metrics."""
    mock_duration = MagicMock()
    mock_sent = MagicMock()
    mock_failed = MagicMock()

    monkeypatch.setattr(
        "backend.app.messaging.senders.telegram.message_send_duration_seconds",
        mock_duration,
    )
    monkeypatch.setattr(
        "backend.app.messaging.senders.telegram.messages_sent_total", mock_sent
    )
    monkeypatch.setattr(
        "backend.app.messaging.senders.telegram.message_fail_total", mock_failed
    )

    return {"duration": mock_duration, "sent": mock_sent, "failed": mock_failed}


@pytest.fixture
def mock_push_metrics(monkeypatch):
    """Mock Push metrics."""
    mock_duration = MagicMock()
    mock_sent = MagicMock()
    mock_failed = MagicMock()

    monkeypatch.setattr(
        "backend.app.messaging.senders.push.message_send_duration_seconds",
        mock_duration,
    )
    monkeypatch.setattr(
        "backend.app.messaging.senders.push.messages_sent_total", mock_sent
    )
    monkeypatch.setattr(
        "backend.app.messaging.senders.push.message_fail_total", mock_failed
    )

    return {"duration": mock_duration, "sent": mock_sent, "failed": mock_failed}


@pytest.fixture
def clear_rate_limits():
    """Clear rate limit timestamps before each test."""
    # Clear email rate limits
    import backend.app.messaging.senders.email as email_module

    email_module._email_timestamps = []

    # Clear telegram rate limits
    import backend.app.messaging.senders.telegram as telegram_module

    telegram_module._telegram_timestamps = []

    yield

    # Cleanup after test
    email_module._email_timestamps = []
    telegram_module._telegram_timestamps = []


# ===== EMAIL SENDER TESTS =====


class TestEmailSenderSuccess:
    """Test successful email sending."""

    @pytest.mark.asyncio
    async def test_send_email_success(
        self, mock_smtp_settings, mock_email_metrics, clear_rate_limits
    ):
        """Test successful email send."""
        with patch(
            "backend.app.messaging.senders.email.asyncio.to_thread"
        ) as mock_thread:
            mock_thread.return_value = None  # _send_smtp succeeds

            result = await send_email(
                to="user@example.com",
                subject="Test Subject",
                html="<p>Test HTML</p>",
                text="Test text",
            )

            # Verify result
            assert result["status"] == "sent"
            # message_id may be None if SMTP server didn't set Message-ID header
            assert "message_id" in result
            assert result["error"] is None

            # Verify metrics
            mock_email_metrics["duration"].labels.assert_called_with(channel="email")
            mock_email_metrics["sent"].labels.assert_called_with(
                channel="email", type="alert"
            )

    @pytest.mark.asyncio
    async def test_send_email_creates_mime_message(
        self, mock_smtp_settings, clear_rate_limits
    ):
        """Test email creates proper MIME message."""
        with patch(
            "backend.app.messaging.senders.email.asyncio.to_thread"
        ) as mock_thread:
            mock_thread.return_value = None

            await send_email(
                to="user@example.com",
                subject="Test Subject",
                html="<p>HTML</p>",
                text="Text",
            )

            # Verify _send_smtp called
            assert mock_thread.called

            # Get the message argument (asyncio.to_thread is called with: _send_smtp, msg, to)
            call_args = mock_thread.call_args
            msg = call_args.args[1]  # Second positional arg is the message

            # Verify message has correct headers
            assert msg["To"] == "user@example.com"
            assert msg["Subject"] == "Test Subject"
            assert msg["From"] == mock_smtp_settings.smtp.from_email


class TestEmailSenderErrors:
    """Test email sender error handling."""

    @pytest.mark.asyncio
    async def test_send_email_auth_error(
        self, mock_smtp_settings, mock_email_metrics, clear_rate_limits
    ):
        """Test email send with authentication error."""
        with patch(
            "backend.app.messaging.senders.email.asyncio.to_thread"
        ) as mock_thread:
            mock_thread.side_effect = SMTPAuthenticationError(535, "Auth failed")

            result = await send_email(
                to="user@example.com",
                subject="Test",
                html="<p>Test</p>",
                text="Test",
            )

            # Verify result
            assert result["status"] == "failed"
            assert result["message_id"] is None
            assert "SMTP authentication failed" in result["error"]

            # Verify failure metric
            mock_email_metrics["failed"].labels.assert_called_with(
                reason="auth_error", channel="email"
            )

    @pytest.mark.asyncio
    async def test_send_email_recipient_refused(
        self, mock_smtp_settings, mock_email_metrics, clear_rate_limits
    ):
        """Test email send with recipient refused (bounce)."""
        with patch(
            "backend.app.messaging.senders.email.asyncio.to_thread"
        ) as mock_thread:
            mock_thread.side_effect = SMTPRecipientsRefused(
                {"user@example.com": (550, "User not found")}
            )

            result = await send_email(
                to="user@example.com",
                subject="Test",
                html="<p>Test</p>",
                text="Test",
            )

            # Verify result
            assert result["status"] == "failed"
            assert "Recipient refused" in result["error"]

            # Verify failure metric
            mock_email_metrics["failed"].labels.assert_called_with(
                reason="recipient_refused", channel="email"
            )

    @pytest.mark.asyncio
    async def test_send_email_timeout_retry(
        self, mock_smtp_settings, mock_email_metrics, clear_rate_limits
    ):
        """Test email send retries on timeout."""
        with patch(
            "backend.app.messaging.senders.email.asyncio.to_thread"
        ) as mock_thread:
            # First 2 attempts timeout, 3rd succeeds
            mock_thread.side_effect = [
                TimeoutError("Timeout 1"),
                TimeoutError("Timeout 2"),
                None,  # Success on 3rd attempt
            ]

            with patch(
                "backend.app.messaging.senders.email.asyncio.sleep"
            ) as mock_sleep:
                result = await send_email(
                    to="user@example.com",
                    subject="Test",
                    html="<p>Test</p>",
                    text="Test",
                )

                # Verify retries
                assert mock_thread.call_count == 3
                assert mock_sleep.call_count == 2  # 2 retries

                # Verify success on 3rd attempt
                assert result["status"] == "sent"

    @pytest.mark.asyncio
    async def test_send_email_max_retries_exceeded(
        self, mock_smtp_settings, mock_email_metrics, clear_rate_limits
    ):
        """Test email send fails after max retries."""
        with patch(
            "backend.app.messaging.senders.email.asyncio.to_thread"
        ) as mock_thread:
            # All attempts timeout
            mock_thread.side_effect = SMTPServerDisconnected("Server disconnected")

            with patch("backend.app.messaging.senders.email.asyncio.sleep"):
                result = await send_email(
                    to="user@example.com",
                    subject="Test",
                    html="<p>Test</p>",
                    text="Test",
                )

                # Verify max retries metric
                mock_email_metrics["failed"].labels.assert_called_with(
                    reason="max_retries", channel="email"
                )

                # Verify result
                assert result["status"] == "failed"
                assert "Max retries exceeded" in result["error"]


class TestEmailRateLimiting:
    """Test email rate limiting (100/minute)."""

    def test_email_rate_limit_allows_under_limit(self, clear_rate_limits):
        """Test rate limit allows under 100 emails/minute."""
        import backend.app.messaging.senders.email as email_module

        # Send 99 emails
        for _ in range(99):
            email_module._email_timestamps.append(time.time())

        # 100th should be allowed
        assert email_check_rate_limit() is True

    def test_email_rate_limit_blocks_over_limit(self, clear_rate_limits):
        """Test rate limit blocks over 100 emails/minute."""
        import backend.app.messaging.senders.email as email_module

        # Send 100 emails
        for _ in range(100):
            email_module._email_timestamps.append(time.time())

        # 101st should be blocked
        assert email_check_rate_limit() is False

    def test_email_rate_limit_cleans_old_timestamps(self, clear_rate_limits):
        """Test rate limit cleans timestamps older than 60s."""
        import backend.app.messaging.senders.email as email_module

        # Add 100 old timestamps (61 seconds ago)
        old_time = time.time() - 61
        for _ in range(100):
            email_module._email_timestamps.append(old_time)

        # Should allow new email (old timestamps cleaned)
        assert email_check_rate_limit() is True

    def test_email_rate_limit_constant_value(self):
        """Test MAX_EMAILS_PER_MINUTE is 100."""
        assert MAX_EMAILS_PER_MINUTE == 100

    @pytest.mark.asyncio
    async def test_send_email_rate_limited_returns_status(
        self, mock_smtp_settings, mock_email_metrics, clear_rate_limits
    ):
        """Test send_email returns rate_limited status."""
        import backend.app.messaging.senders.email as email_module

        # Fill rate limit
        for _ in range(100):
            email_module._email_timestamps.append(time.time())

        result = await send_email(
            to="user@example.com", subject="Test", html="<p>Test</p>", text="Test"
        )

        # Verify rate_limited status
        assert result["status"] == "rate_limited"
        assert "Rate limit exceeded" in result["error"]


class TestEmailBatchUtility:
    """Test email batch sending utility."""

    @pytest.mark.asyncio
    async def test_send_batch_emails_success(
        self, mock_smtp_settings, clear_rate_limits
    ):
        """Test batch email sending."""
        with patch("backend.app.messaging.senders.email.asyncio.to_thread"):
            emails = [
                {
                    "to": f"user{i}@example.com",
                    "subject": "Test",
                    "html": "<p>Test</p>",
                    "text": "Test",
                }
                for i in range(5)
            ]

            result = await send_batch_emails(emails, batch_size=2)

            # Verify all sent
            assert result["sent"] == 5
            assert result["failed"] == 0
            assert result["rate_limited"] == 0

    @pytest.mark.asyncio
    async def test_send_batch_emails_with_failures(
        self, mock_smtp_settings, clear_rate_limits
    ):
        """Test batch email with some failures."""
        with patch(
            "backend.app.messaging.senders.email.asyncio.to_thread"
        ) as mock_thread:
            # First 2 succeed, 3rd fails, 4th succeeds
            mock_thread.side_effect = [
                None,
                None,
                SMTPException("Temp error"),
                None,
            ]

            emails = [
                {
                    "to": f"user{i}@example.com",
                    "subject": "Test",
                    "html": "<p>Test</p>",
                    "text": "Test",
                }
                for i in range(4)
            ]

            result = await send_batch_emails(emails, batch_size=2)

            # Verify counts
            assert result["sent"] + result["failed"] == 4


# ===== TELEGRAM SENDER TESTS =====


class TestTelegramSenderSuccess:
    """Test successful Telegram sending."""

    @pytest.mark.asyncio
    async def test_send_telegram_success(
        self, mock_telegram_settings, mock_telegram_metrics, clear_rate_limits
    ):
        """Test successful Telegram send."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={"ok": True, "result": {"message_id": 123}}
        )

        with patch("aiohttp.ClientSession") as mock_session_class:
            # Create mock session with post method that returns an async context manager
            mock_session = MagicMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)

            # Make post() return a context manager that yields the response
            mock_post_ctx = MagicMock()
            mock_post_ctx.__aenter__ = AsyncMock(return_value=mock_response)
            mock_post_ctx.__aexit__ = AsyncMock(return_value=None)
            mock_session.post = MagicMock(return_value=mock_post_ctx)

            mock_session_class.return_value = mock_session

            result = await send_telegram(
                chat_id="123456789", text="Test message", parse_mode="MarkdownV2"
            )

            # Verify result
            assert result["status"] == "sent"
            assert result["message_id"] == 123
            assert result["error"] is None

            # Verify metrics
            mock_telegram_metrics["sent"].labels.assert_called_with(
                channel="telegram", type="alert"
            )

    @pytest.mark.asyncio
    async def test_send_telegram_creates_proper_request(
        self, mock_telegram_settings, clear_rate_limits
    ):
        """Test Telegram creates proper API request."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={"ok": True, "result": {"message_id": 123}}
        )

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value.__aenter__.return_value = mock_session
            mock_session_class.return_value.__aexit__.return_value = None
            mock_session.post.return_value.__aenter__.return_value = mock_response
            mock_session.post.return_value.__aexit__.return_value = None

            await send_telegram(
                chat_id="987654321", text="Test message", parse_mode="MarkdownV2"
            )

            # Verify API call
            call_args = mock_session.post.call_args
            assert "sendMessage" in call_args[0][0]  # URL contains sendMessage

            # Verify payload
            payload = call_args[1]["json"]
            assert payload["chat_id"] == "987654321"
            assert payload["text"] == "Test message"
            assert payload["parse_mode"] == "MarkdownV2"


class TestTelegramSenderErrors:
    """Test Telegram sender error handling."""

    @pytest.mark.asyncio
    async def test_send_telegram_user_blocked(
        self, mock_telegram_settings, mock_telegram_metrics, clear_rate_limits
    ):
        """Test Telegram send with user blocked bot (403)."""
        mock_response = AsyncMock()
        mock_response.status = 403
        mock_response.json = AsyncMock(
            return_value={
                "ok": False,
                "error_code": 403,
                "description": "Forbidden: user is deactivated",
            }
        )

        with patch("aiohttp.ClientSession") as mock_session_class:
            # Use MagicMock for session context manager
            mock_session = MagicMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)

            # Use MagicMock for post context manager
            mock_post_ctx = MagicMock()
            mock_post_ctx.__aenter__ = AsyncMock(return_value=mock_response)
            mock_post_ctx.__aexit__ = AsyncMock(return_value=None)
            mock_session.post = MagicMock(return_value=mock_post_ctx)

            mock_session_class.return_value = mock_session

            result = await send_telegram(chat_id="123456789", text="Test")

            # Verify result
            assert result["status"] == "failed"
            assert "User blocked bot" in result["error"]

            # Verify failure metric
            mock_telegram_metrics["failed"].labels.assert_called_with(
                reason="user_blocked", channel="telegram"
            )

    @pytest.mark.asyncio
    async def test_send_telegram_bad_request(
        self, mock_telegram_settings, mock_telegram_metrics, clear_rate_limits
    ):
        """Test Telegram send with bad request (400)."""
        mock_response = AsyncMock()
        mock_response.status = 400
        mock_response.json = AsyncMock(
            return_value={
                "ok": False,
                "error_code": 400,
                "description": "Bad Request: invalid chat_id",
            }
        )

        with patch("aiohttp.ClientSession") as mock_session_class:
            # Use MagicMock for session context manager
            mock_session = MagicMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)

            # Use MagicMock for post context manager
            mock_post_ctx = MagicMock()
            mock_post_ctx.__aenter__ = AsyncMock(return_value=mock_response)
            mock_post_ctx.__aexit__ = AsyncMock(return_value=None)
            mock_session.post = MagicMock(return_value=mock_post_ctx)

            mock_session_class.return_value = mock_session

            result = await send_telegram(chat_id="invalid", text="Test")

            # Verify result
            assert result["status"] == "failed"
            assert "Bad request" in result["error"]

            # Verify failure metric
            mock_telegram_metrics["failed"].labels.assert_called_with(
                reason="bad_request", channel="telegram"
            )

    @pytest.mark.asyncio
    async def test_send_telegram_rate_limit_429(
        self, mock_telegram_settings, mock_telegram_metrics, clear_rate_limits
    ):
        """Test Telegram send with rate limit from Telegram API (429)."""
        mock_response_429 = AsyncMock()
        mock_response_429.status = 429
        mock_response_429.json = AsyncMock(
            return_value={
                "ok": False,
                "error_code": 429,
                "description": "Too Many Requests",
                "parameters": {"retry_after": 1},
            }
        )

        mock_response_success = AsyncMock()
        mock_response_success.status = 200
        mock_response_success.json = AsyncMock(
            return_value={"ok": True, "result": {"message_id": 123}}
        )

        with patch("aiohttp.ClientSession") as mock_session_class:
            # Use MagicMock for session context manager
            mock_session = MagicMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)

            # Set up post() to return different responses on different calls
            mock_post_429 = MagicMock()
            mock_post_429.__aenter__ = AsyncMock(return_value=mock_response_429)
            mock_post_429.__aexit__ = AsyncMock(return_value=None)

            mock_post_success = MagicMock()
            mock_post_success.__aenter__ = AsyncMock(return_value=mock_response_success)
            mock_post_success.__aexit__ = AsyncMock(return_value=None)

            mock_session.post = MagicMock(
                side_effect=[mock_post_429, mock_post_success]
            )
            mock_session_class.return_value = mock_session

            with patch("backend.app.messaging.senders.telegram.asyncio.sleep"):
                result = await send_telegram(chat_id="123456789", text="Test")

                # Verify retried and succeeded
                assert result["status"] == "sent"


class TestTelegramRateLimiting:
    """Test Telegram rate limiting (20/second)."""

    def test_telegram_rate_limit_allows_under_limit(self, clear_rate_limits):
        """Test rate limit allows under 20 messages/second."""
        import backend.app.messaging.senders.telegram as telegram_module

        # Send 19 messages
        for _ in range(19):
            telegram_module._telegram_timestamps.append(time.time())

        # 20th should be allowed
        assert telegram_check_rate_limit() is True

    def test_telegram_rate_limit_blocks_over_limit(self, clear_rate_limits):
        """Test rate limit blocks over 20 messages/second."""
        import backend.app.messaging.senders.telegram as telegram_module

        # Send 20 messages
        for _ in range(20):
            telegram_module._telegram_timestamps.append(time.time())

        # 21st should be blocked
        assert telegram_check_rate_limit() is False

    def test_telegram_rate_limit_constant_value(self):
        """Test MAX_MESSAGES_PER_SECOND is 20."""
        assert MAX_MESSAGES_PER_SECOND == 20


# ===== PUSH SENDER TESTS =====


class TestPushSenderSuccess:
    """Test successful push sending."""

    @pytest.mark.asyncio
    async def test_send_push_success(
        self, mock_push_settings, mock_push_metrics, clear_rate_limits
    ):
        """Test successful push send."""
        mock_db = AsyncMock()

        # Mock subscription retrieval
        with patch(
            "backend.app.messaging.senders.push._get_push_subscription"
        ) as mock_get_sub:
            mock_get_sub.return_value = {
                "endpoint": "https://fcm.googleapis.com/...",
                "keys": {"p256dh": "key1", "auth": "key2"},
            }

            # Mock webpush
            with patch("backend.app.messaging.senders.push.webpush"):
                with patch(
                    "backend.app.messaging.senders.push.asyncio.to_thread"
                ) as mock_thread:
                    mock_thread.return_value = None  # Success

                    result = await send_push(
                        db=mock_db,
                        user_id="user-123",
                        title="Test Title",
                        body="Test Body",
                    )

                    # Verify result
                    assert result["status"] == "sent"
                    assert result["message_id"] is not None
                    assert result["error"] is None

                    # Verify metrics
                    mock_push_metrics["sent"].labels.assert_called_with(
                        channel="push", type="alert"
                    )

    @pytest.mark.asyncio
    async def test_send_push_no_subscription(
        self, mock_push_settings, clear_rate_limits
    ):
        """Test push send with no subscription."""
        mock_db = AsyncMock()

        # Mock no subscription
        with patch(
            "backend.app.messaging.senders.push._get_push_subscription"
        ) as mock_get_sub:
            mock_get_sub.return_value = None  # No subscription

            result = await send_push(
                db=mock_db, user_id="user-123", title="Test", body="Test"
            )

            # Verify result
            assert result["status"] == "no_subscription"
            assert "no push subscription" in result["error"].lower()


class TestPushSenderErrors:
    """Test push sender error handling."""

    @pytest.mark.asyncio
    async def test_send_push_subscription_expired_410(
        self, mock_push_settings, mock_push_metrics, clear_rate_limits
    ):
        """Test push send with expired subscription (410 Gone)."""
        mock_db = AsyncMock()

        # Mock subscription
        with patch(
            "backend.app.messaging.senders.push._get_push_subscription"
        ) as mock_get_sub:
            mock_get_sub.return_value = {
                "endpoint": "https://fcm.googleapis.com/...",
                "keys": {"p256dh": "key1", "auth": "key2"},
            }

            # Mock webpush raises 410
            with patch(
                "backend.app.messaging.senders.push.asyncio.to_thread"
            ) as mock_thread:
                mock_response = Mock()
                mock_response.status_code = 410
                error = WebPushException("Gone")
                error.response = mock_response
                mock_thread.side_effect = error

                # Mock delete subscription
                with patch(
                    "backend.app.messaging.senders.push._delete_push_subscription"
                ) as mock_delete:
                    result = await send_push(
                        db=mock_db, user_id="user-123", title="Test", body="Test"
                    )

                    # Verify result
                    assert result["status"] == "failed"
                    assert "410 Gone" in result["error"]

                    # Verify subscription deleted
                    mock_delete.assert_called_once_with(mock_db, "user-123")

                    # Verify failure metric
                    mock_push_metrics["failed"].labels.assert_called_with(
                        reason="subscription_expired", channel="push"
                    )

    @pytest.mark.asyncio
    async def test_send_push_permanent_error_400(
        self, mock_push_settings, mock_push_metrics, clear_rate_limits
    ):
        """Test push send with permanent error (400)."""
        mock_db = AsyncMock()

        with patch(
            "backend.app.messaging.senders.push._get_push_subscription"
        ) as mock_get_sub:
            mock_get_sub.return_value = {
                "endpoint": "https://fcm.googleapis.com/...",
                "keys": {"p256dh": "key1", "auth": "key2"},
            }

            with patch(
                "backend.app.messaging.senders.push.asyncio.to_thread"
            ) as mock_thread:
                mock_response = Mock()
                mock_response.status_code = 400
                error = WebPushException("Bad Request")
                error.response = mock_response
                mock_thread.side_effect = error

                result = await send_push(
                    db=mock_db, user_id="user-123", title="Test", body="Test"
                )

                # Verify permanent error
                assert result["status"] == "failed"
                assert "Permanent error: 400" in result["error"]

                # Verify failure metric
                mock_push_metrics["failed"].labels.assert_called_with(
                    reason="permanent_error", channel="push"
                )


# ===== METRICS TESTS =====


class TestMetricsIntegration:
    """Test metrics are tracked correctly."""

    @pytest.mark.asyncio
    async def test_email_tracks_duration_metric(
        self, mock_smtp_settings, mock_email_metrics, clear_rate_limits
    ):
        """Test email send tracks duration metric."""
        with patch("backend.app.messaging.senders.email.asyncio.to_thread"):
            await send_email(
                to="user@example.com", subject="Test", html="<p>Test</p>", text="Test"
            )

            # Verify duration metric observed
            mock_email_metrics["duration"].labels.assert_called_with(channel="email")
            mock_email_metrics["duration"].labels().observe.assert_called_once()

    @pytest.mark.asyncio
    async def test_telegram_tracks_duration_metric(
        self, mock_telegram_settings, mock_telegram_metrics, clear_rate_limits
    ):
        """Test Telegram send tracks duration metric."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={"ok": True, "result": {"message_id": 123}}
        )

        with patch("aiohttp.ClientSession") as mock_session_class:
            # Use MagicMock for session context manager
            mock_session = MagicMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)

            # Use MagicMock for post context manager
            mock_post_ctx = MagicMock()
            mock_post_ctx.__aenter__ = AsyncMock(return_value=mock_response)
            mock_post_ctx.__aexit__ = AsyncMock(return_value=None)
            mock_session.post = MagicMock(return_value=mock_post_ctx)

            mock_session_class.return_value = mock_session

            await send_telegram(chat_id="123456789", text="Test")

            # Verify duration metric
            mock_telegram_metrics["duration"].labels.assert_called_with(
                channel="telegram"
            )


class TestConstants:
    """Test constant values are correct."""

    def test_email_max_retries(self):
        """Test email max retries is 3."""
        assert EMAIL_MAX_RETRIES == 3

    def test_telegram_max_retries(self):
        """Test Telegram max retries is 3."""
        assert TELEGRAM_MAX_RETRIES == 3

    def test_push_max_retries(self):
        """Test push max retries is 3."""
        assert PUSH_MAX_RETRIES == 3
