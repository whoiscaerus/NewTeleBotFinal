"""Tests for GuideBot scheduler.

Tests the periodic guide posting functionality including job scheduling,
error handling, database logging, and configuration.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Bot
from telegram.error import TelegramError

from backend.app.telegram.scheduler import GuideScheduler


class TestGuideSchedulerInitialization:
    """Test GuideScheduler initialization."""

    def test_init_with_defaults(self):
        """Test scheduler initialization with default parameters."""
        bot = MagicMock(spec=Bot)
        chat_ids = [-1001234567890]

        scheduler = GuideScheduler(bot=bot, guide_chat_ids=chat_ids)

        assert scheduler.bot == bot
        assert scheduler.guide_chat_ids == chat_ids
        assert scheduler.interval_hours == 4
        assert scheduler.is_running is False

    def test_init_with_custom_interval(self):
        """Test scheduler initialization with custom interval."""
        bot = MagicMock(spec=Bot)
        chat_ids = [-1001234567890, -1001234567891]

        scheduler = GuideScheduler(
            bot=bot,
            guide_chat_ids=chat_ids,
            interval_hours=8,
        )

        assert scheduler.interval_hours == 8
        assert len(scheduler.guide_chat_ids) == 2

    def test_init_with_db_session(self):
        """Test scheduler initialization with database session."""
        bot = MagicMock(spec=Bot)
        db_session = MagicMock()

        scheduler = GuideScheduler(
            bot=bot,
            guide_chat_ids=[-1001234567890],
            db_session=db_session,
        )

        assert scheduler.db_session == db_session

    def test_init_default_guides_available(self):
        """Test that default guides are available."""
        assert len(GuideScheduler.DEFAULT_GUIDES) >= 4
        assert all("id" in guide for guide in GuideScheduler.DEFAULT_GUIDES)
        assert all("title" in guide for guide in GuideScheduler.DEFAULT_GUIDES)


class TestGuideSchedulerStartStop:
    """Test scheduler start/stop functionality."""

    def test_start_scheduler(self):
        """Test starting the scheduler."""
        bot = MagicMock(spec=Bot)

        scheduler = GuideScheduler(bot=bot, guide_chat_ids=[-1001234567890])

        with patch.object(scheduler.scheduler, "add_job"):
            with patch.object(scheduler.scheduler, "start"):
                scheduler.start()

        assert scheduler.is_running is True

    def test_start_scheduler_already_running(self):
        """Test starting scheduler when already running."""
        bot = MagicMock(spec=Bot)
        scheduler = GuideScheduler(bot=bot, guide_chat_ids=[-1001234567890])
        scheduler.is_running = True

        with patch.object(scheduler.scheduler, "start") as mock_start:
            scheduler.start()

        mock_start.assert_not_called()

    def test_stop_scheduler(self):
        """Test stopping the scheduler."""
        bot = MagicMock(spec=Bot)
        scheduler = GuideScheduler(bot=bot, guide_chat_ids=[-1001234567890])
        scheduler.is_running = True

        with patch.object(scheduler.scheduler, "shutdown"):
            scheduler.stop()

        assert scheduler.is_running is False

    def test_stop_scheduler_not_running(self):
        """Test stopping scheduler when not running."""
        bot = MagicMock(spec=Bot)
        scheduler = GuideScheduler(bot=bot, guide_chat_ids=[-1001234567890])
        scheduler.is_running = False

        with patch.object(scheduler.scheduler, "shutdown") as mock_shutdown:
            scheduler.stop()

        mock_shutdown.assert_not_called()


@pytest.mark.asyncio
class TestGuidePosting:
    """Test guide posting functionality."""

    @pytest.mark.asyncio
    async def test_post_guide_success(self):
        """Test successful guide posting."""
        bot = AsyncMock(spec=Bot)
        chat_ids = [-1001234567890, -1001234567891]

        # Mock message response
        message = MagicMock()
        message.message_id = 123
        bot.send_message.return_value = message

        scheduler = GuideScheduler(bot=bot, guide_chat_ids=chat_ids)

        await scheduler._post_guide()

        # Verify send_message was called for each chat
        assert bot.send_message.call_count == 2

        # Verify arguments
        for call in bot.send_message.call_args_list:
            assert "chat_id" in call.kwargs
            assert call.kwargs["chat_id"] in chat_ids
            assert "text" in call.kwargs
            assert "reply_markup" in call.kwargs

    @pytest.mark.asyncio
    async def test_post_guide_partial_failure(self):
        """Test guide posting with some failures."""
        bot = AsyncMock(spec=Bot)
        chat_ids = [-1001234567890, -1001234567891, -1001234567892]

        # First succeeds, second fails, third succeeds
        message = MagicMock()
        message.message_id = 123

        side_effects = [
            message,
            TelegramError("Chat not found"),
            message,
        ]
        bot.send_message.side_effect = side_effects

        scheduler = GuideScheduler(bot=bot, guide_chat_ids=chat_ids)

        await scheduler._post_guide()

        assert bot.send_message.call_count == 3

    @pytest.mark.asyncio
    async def test_post_guide_rotation(self):
        """Test that guides rotate through available options."""
        bot = AsyncMock(spec=Bot)
        message = MagicMock()
        message.message_id = 123
        bot.send_message.return_value = message

        scheduler = GuideScheduler(bot=bot, guide_chat_ids=[-1001234567890])
        initial_index = scheduler.last_guide_index

        await scheduler._post_guide()
        after_first = scheduler.last_guide_index

        assert after_first == (initial_index + 1) % len(GuideScheduler.DEFAULT_GUIDES)

        # Verify we get different guides on repeated calls
        guides_posted = []
        for _ in range(len(GuideScheduler.DEFAULT_GUIDES)):
            await scheduler._post_guide()
            guides_posted.append(scheduler.last_guide_index)

        # Should have cycled through all guides
        assert len(set(guides_posted)) == len(GuideScheduler.DEFAULT_GUIDES)

    @pytest.mark.asyncio
    async def test_post_guide_all_failures(self):
        """Test guide posting when all chat posts fail."""
        bot = AsyncMock(spec=Bot)
        chat_ids = [-1001234567890, -1001234567891]

        bot.send_message.side_effect = TelegramError("Service unavailable")

        scheduler = GuideScheduler(bot=bot, guide_chat_ids=chat_ids)

        # Should not raise exception
        await scheduler._post_guide()

        assert bot.send_message.call_count == 2


class TestGuideSchedulerJobManagement:
    """Test job status and management."""

    def test_get_job_status_not_scheduled(self):
        """Test getting status when job is not scheduled."""
        bot = MagicMock(spec=Bot)
        scheduler = GuideScheduler(bot=bot, guide_chat_ids=[-1001234567890])

        with patch.object(scheduler.scheduler, "get_job", return_value=None):
            status = scheduler.get_job_status()

        assert status["status"] == "not_scheduled"

    def test_get_job_status_scheduled(self):
        """Test getting status when job is scheduled."""
        bot = MagicMock(spec=Bot)
        scheduler = GuideScheduler(bot=bot, guide_chat_ids=[-1001234567890])

        # Mock job
        mock_job = MagicMock()
        mock_job.next_run_time = datetime.now()
        mock_job.last_run_time = datetime.now()

        with patch.object(scheduler.scheduler, "get_job", return_value=mock_job):
            status = scheduler.get_job_status()

        assert status["status"] == "scheduled"
        assert "next_run_time" in status
        assert "last_execution_time" in status

    def test_get_next_run_time(self):
        """Test getting next run time."""
        bot = MagicMock(spec=Bot)
        scheduler = GuideScheduler(bot=bot, guide_chat_ids=[-1001234567890])

        expected_time = datetime.now()
        mock_job = MagicMock()
        mock_job.next_run_time = expected_time

        with patch.object(scheduler.scheduler, "get_job", return_value=mock_job):
            next_run = scheduler.get_next_run_time()

        assert next_run == expected_time

    def test_get_next_run_time_no_job(self):
        """Test getting next run time when no job scheduled."""
        bot = MagicMock(spec=Bot)
        scheduler = GuideScheduler(bot=bot, guide_chat_ids=[-1001234567890])

        with patch.object(scheduler.scheduler, "get_job", return_value=None):
            next_run = scheduler.get_next_run_time()

        assert next_run is None


class TestGuideSchedulerCreation:
    """Test factory methods for creating scheduler."""

    def test_create_from_env_valid_json(self):
        """Test creating scheduler from valid environment configuration."""
        bot = MagicMock(spec=Bot)
        chat_ids_json = "[-1001234567890, -1001234567891]"

        scheduler = GuideScheduler.create_from_env(
            bot=bot,
            guides_chat_ids_json=chat_ids_json,
        )

        assert scheduler.guide_chat_ids == [-1001234567890, -1001234567891]

    def test_create_from_env_single_chat(self):
        """Test creating scheduler with single chat ID."""
        bot = MagicMock(spec=Bot)
        chat_ids_json = "[-1001234567890]"

        scheduler = GuideScheduler.create_from_env(
            bot=bot,
            guides_chat_ids_json=chat_ids_json,
        )

        assert scheduler.guide_chat_ids == [-1001234567890]

    def test_create_from_env_with_db_session(self):
        """Test creating scheduler from env with database session."""
        bot = MagicMock(spec=Bot)
        db_session = MagicMock()
        chat_ids_json = "[-1001234567890]"

        scheduler = GuideScheduler.create_from_env(
            bot=bot,
            guides_chat_ids_json=chat_ids_json,
            db_session=db_session,
        )

        assert scheduler.db_session == db_session

    def test_create_from_env_invalid_json(self):
        """Test creating scheduler from invalid JSON."""
        bot = MagicMock(spec=Bot)

        with pytest.raises(ValueError, match="Invalid GUIDES_CHAT_IDS_JSON"):
            GuideScheduler.create_from_env(
                bot=bot,
                guides_chat_ids_json="invalid json",
            )

    def test_create_from_env_not_array(self):
        """Test creating scheduler when JSON is not array."""
        bot = MagicMock(spec=Bot)

        with pytest.raises(ValueError, match="must be a JSON array"):
            GuideScheduler.create_from_env(
                bot=bot,
                guides_chat_ids_json='{"chat_id": 123}',
            )


@pytest.mark.asyncio
class TestErrorHandling:
    """Test error handling in scheduler."""

    @pytest.mark.asyncio
    async def test_telegram_error_handling(self):
        """Test handling of Telegram API errors."""
        bot = AsyncMock(spec=Bot)
        bot.send_message.side_effect = TelegramError("API error")

        scheduler = GuideScheduler(bot=bot, guide_chat_ids=[-1001234567890])

        # Should not raise
        await scheduler._post_guide()

    @pytest.mark.asyncio
    async def test_unexpected_error_handling(self):
        """Test handling of unexpected errors."""
        bot = AsyncMock(spec=Bot)
        bot.send_message.side_effect = Exception("Unexpected error")

        scheduler = GuideScheduler(bot=bot, guide_chat_ids=[-1001234567890])

        # Should not raise
        await scheduler._post_guide()

    def test_start_error_handling(self):
        """Test error handling when starting scheduler."""
        bot = MagicMock(spec=Bot)
        scheduler = GuideScheduler(bot=bot, guide_chat_ids=[-1001234567890])

        with patch.object(
            scheduler.scheduler, "add_job", side_effect=Exception("Error")
        ):
            with pytest.raises(Exception):
                scheduler.start()

    def test_stop_error_handling(self):
        """Test error handling when stopping scheduler."""
        bot = MagicMock(spec=Bot)
        scheduler = GuideScheduler(bot=bot, guide_chat_ids=[-1001234567890])
        scheduler.is_running = True

        with patch.object(
            scheduler.scheduler, "shutdown", side_effect=Exception("Error")
        ):
            with pytest.raises(Exception):
                scheduler.stop()
