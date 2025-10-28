"""Tests for marketing scheduler and clicks store.

Tests the periodic promo posting and user click tracking functionality.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Bot
from telegram.error import TelegramError

from backend.app.marketing.clicks_store import ClicksStore
from backend.app.marketing.scheduler import MarketingScheduler


class TestMarketingSchedulerInitialization:
    """Test MarketingScheduler initialization."""

    def test_init_with_defaults(self):
        """Test scheduler initialization with default parameters."""
        bot = MagicMock(spec=Bot)
        chat_ids = [-1001234567890]

        scheduler = MarketingScheduler(bot=bot, promo_chat_ids=chat_ids)

        assert scheduler.bot == bot
        assert scheduler.promo_chat_ids == chat_ids
        assert scheduler.interval_hours == 4
        assert scheduler.is_running is False

    def test_init_with_custom_interval(self):
        """Test scheduler initialization with custom interval."""
        bot = MagicMock(spec=Bot)
        chat_ids = [-1001234567890, -1001234567891]

        scheduler = MarketingScheduler(
            bot=bot,
            promo_chat_ids=chat_ids,
            interval_hours=8,
        )

        assert scheduler.interval_hours == 8
        assert len(scheduler.promo_chat_ids) == 2

    def test_init_with_db_session(self):
        """Test scheduler initialization with database session."""
        bot = MagicMock(spec=Bot)
        db_session = MagicMock()

        scheduler = MarketingScheduler(
            bot=bot,
            promo_chat_ids=[-1001234567890],
            db_session=db_session,
        )

        assert scheduler.db_session == db_session

    def test_init_default_promos_available(self):
        """Test that default promos are available."""
        assert len(MarketingScheduler.DEFAULT_PROMOS) >= 4
        assert all("id" in promo for promo in MarketingScheduler.DEFAULT_PROMOS)
        assert all("title" in promo for promo in MarketingScheduler.DEFAULT_PROMOS)


class TestMarketingSchedulerStartStop:
    """Test scheduler start/stop functionality."""

    def test_start_scheduler(self):
        """Test starting the scheduler."""
        bot = MagicMock(spec=Bot)

        scheduler = MarketingScheduler(bot=bot, promo_chat_ids=[-1001234567890])

        with patch.object(scheduler.scheduler, "add_job"):
            with patch.object(scheduler.scheduler, "start"):
                scheduler.start()

        assert scheduler.is_running is True

    def test_start_scheduler_already_running(self):
        """Test starting scheduler when already running."""
        bot = MagicMock(spec=Bot)
        scheduler = MarketingScheduler(bot=bot, promo_chat_ids=[-1001234567890])
        scheduler.is_running = True

        with patch.object(scheduler.scheduler, "start") as mock_start:
            scheduler.start()

        mock_start.assert_not_called()

    def test_stop_scheduler(self):
        """Test stopping the scheduler."""
        bot = MagicMock(spec=Bot)
        scheduler = MarketingScheduler(bot=bot, promo_chat_ids=[-1001234567890])
        scheduler.is_running = True

        with patch.object(scheduler.scheduler, "shutdown"):
            scheduler.stop()

        assert scheduler.is_running is False

    def test_stop_scheduler_not_running(self):
        """Test stopping scheduler when not running."""
        bot = MagicMock(spec=Bot)
        scheduler = MarketingScheduler(bot=bot, promo_chat_ids=[-1001234567890])
        scheduler.is_running = False

        with patch.object(scheduler.scheduler, "shutdown") as mock_shutdown:
            scheduler.stop()

        mock_shutdown.assert_not_called()


@pytest.mark.asyncio
class TestPromoPosting:
    """Test promo posting functionality."""

    @pytest.mark.asyncio
    async def test_post_promo_success(self):
        """Test successful promo posting."""
        bot = AsyncMock(spec=Bot)
        chat_ids = [-1001234567890, -1001234567891]

        # Mock message response
        message = MagicMock()
        message.message_id = 123
        bot.send_message.return_value = message

        scheduler = MarketingScheduler(bot=bot, promo_chat_ids=chat_ids)

        await scheduler._post_promo()

        # Verify send_message was called for each chat
        assert bot.send_message.call_count == 2

        # Verify arguments
        for call in bot.send_message.call_args_list:
            assert "chat_id" in call.kwargs
            assert call.kwargs["chat_id"] in chat_ids
            assert "text" in call.kwargs
            assert "reply_markup" in call.kwargs

    @pytest.mark.asyncio
    async def test_post_promo_partial_failure(self):
        """Test promo posting with some failures."""
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

        scheduler = MarketingScheduler(bot=bot, promo_chat_ids=chat_ids)

        await scheduler._post_promo()

        assert bot.send_message.call_count == 3

    @pytest.mark.asyncio
    async def test_post_promo_rotation(self):
        """Test that promos rotate through available options."""
        bot = AsyncMock(spec=Bot)
        message = MagicMock()
        message.message_id = 123
        bot.send_message.return_value = message

        scheduler = MarketingScheduler(bot=bot, promo_chat_ids=[-1001234567890])
        initial_index = scheduler.last_promo_index

        await scheduler._post_promo()
        after_first = scheduler.last_promo_index

        assert after_first == (initial_index + 1) % len(
            MarketingScheduler.DEFAULT_PROMOS
        )

        # Verify we get different promos on repeated calls
        promos_posted = []
        for _ in range(len(MarketingScheduler.DEFAULT_PROMOS)):
            await scheduler._post_promo()
            promos_posted.append(scheduler.last_promo_index)

        # Should have cycled through all promos
        assert len(set(promos_posted)) == len(MarketingScheduler.DEFAULT_PROMOS)

    @pytest.mark.asyncio
    async def test_post_promo_all_failures(self):
        """Test promo posting when all chat posts fail."""
        bot = AsyncMock(spec=Bot)
        chat_ids = [-1001234567890, -1001234567891]

        bot.send_message.side_effect = TelegramError("Service unavailable")

        scheduler = MarketingScheduler(bot=bot, promo_chat_ids=chat_ids)

        # Should not raise exception
        await scheduler._post_promo()

        assert bot.send_message.call_count == 2


class TestMarketingSchedulerJobManagement:
    """Test job status and management."""

    def test_get_job_status_not_scheduled(self):
        """Test getting status when job is not scheduled."""
        bot = MagicMock(spec=Bot)
        scheduler = MarketingScheduler(bot=bot, promo_chat_ids=[-1001234567890])

        with patch.object(scheduler.scheduler, "get_job", return_value=None):
            status = scheduler.get_job_status()

        assert status["status"] == "not_scheduled"

    def test_get_job_status_scheduled(self):
        """Test getting status when job is scheduled."""
        bot = MagicMock(spec=Bot)
        scheduler = MarketingScheduler(bot=bot, promo_chat_ids=[-1001234567890])

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
        scheduler = MarketingScheduler(bot=bot, promo_chat_ids=[-1001234567890])

        expected_time = datetime.now()
        mock_job = MagicMock()
        mock_job.next_run_time = expected_time

        with patch.object(scheduler.scheduler, "get_job", return_value=mock_job):
            next_run = scheduler.get_next_run_time()

        assert next_run == expected_time


class TestMarketingSchedulerCreation:
    """Test factory methods for creating scheduler."""

    def test_create_from_env_valid_json(self):
        """Test creating scheduler from valid environment configuration."""
        bot = MagicMock(spec=Bot)
        chat_ids_json = "[-1001234567890, -1001234567891]"

        scheduler = MarketingScheduler.create_from_env(
            bot=bot,
            promos_chat_ids_json=chat_ids_json,
        )

        assert scheduler.promo_chat_ids == [-1001234567890, -1001234567891]

    def test_create_from_env_single_chat(self):
        """Test creating scheduler with single chat ID."""
        bot = MagicMock(spec=Bot)
        chat_ids_json = "[-1001234567890]"

        scheduler = MarketingScheduler.create_from_env(
            bot=bot,
            promos_chat_ids_json=chat_ids_json,
        )

        assert scheduler.promo_chat_ids == [-1001234567890]

    def test_create_from_env_with_db_session(self):
        """Test creating scheduler from env with database session."""
        bot = MagicMock(spec=Bot)
        db_session = MagicMock()
        chat_ids_json = "[-1001234567890]"

        scheduler = MarketingScheduler.create_from_env(
            bot=bot,
            promos_chat_ids_json=chat_ids_json,
            db_session=db_session,
        )

        assert scheduler.db_session == db_session

    def test_create_from_env_invalid_json(self):
        """Test creating scheduler from invalid JSON."""
        bot = MagicMock(spec=Bot)

        with pytest.raises(ValueError, match="Invalid PROMOS_CHAT_IDS_JSON"):
            MarketingScheduler.create_from_env(
                bot=bot,
                promos_chat_ids_json="invalid json",
            )

    def test_create_from_env_not_array(self):
        """Test creating scheduler when JSON is not array."""
        bot = MagicMock(spec=Bot)

        with pytest.raises(ValueError, match="must be a JSON array"):
            MarketingScheduler.create_from_env(
                bot=bot,
                promos_chat_ids_json='{"chat_id": 123}',
            )


@pytest.mark.asyncio
class TestClicksStore:
    """Test clicks store functionality with real database."""

    @pytest.mark.asyncio
    async def test_log_click_success(self, db_session):
        """Test logging a CTA click."""
        store = ClicksStore(db_session=db_session)

        click_id = await store.log_click(
            user_id="123456789",
            promo_id="promo_1",
            cta_text="Upgrade to Premium",
        )

        assert click_id is not None
        assert isinstance(click_id, str)
        assert len(click_id) > 0

    @pytest.mark.asyncio
    async def test_log_click_with_metadata(self, db_session):
        """Test logging click with metadata."""
        store = ClicksStore(db_session=db_session)

        click_id = await store.log_click(
            user_id="123456789",
            promo_id="promo_1",
            cta_text="Upgrade",
            metadata={"plan": "premium", "source": "channel"},
        )

        assert click_id is not None
        # Verify the click was stored with metadata
        clicks = await store.get_user_clicks(user_id="123456789")
        assert len(clicks) == 1
        assert clicks[0]["metadata"]["plan"] == "premium"
        assert clicks[0]["metadata"]["source"] == "channel"

    @pytest.mark.asyncio
    async def test_get_user_clicks(self, db_session):
        """Test retrieving user's clicks."""
        store = ClicksStore(db_session=db_session)

        # Log some clicks
        await store.log_click(
            user_id="user_123",
            promo_id="promo_1",
            cta_text="Click 1",
        )
        await store.log_click(
            user_id="user_123",
            promo_id="promo_2",
            cta_text="Click 2",
        )
        await store.log_click(
            user_id="user_456",
            promo_id="promo_1",
            cta_text="Click 3",
        )

        # Retrieve user's clicks
        clicks = await store.get_user_clicks(user_id="user_123")

        assert len(clicks) == 2
        assert all(click["user_id"] == "user_123" for click in clicks)
        assert {click["promo_id"] for click in clicks} == {"promo_1", "promo_2"}

    @pytest.mark.asyncio
    async def test_get_promo_clicks(self, db_session):
        """Test retrieving promo's clicks."""
        store = ClicksStore(db_session=db_session)

        # Log clicks for same promo from different users
        await store.log_click(
            user_id="user_1",
            promo_id="promo_1",
            cta_text="Click 1",
        )
        await store.log_click(
            user_id="user_2",
            promo_id="promo_1",
            cta_text="Click 2",
        )
        await store.log_click(
            user_id="user_3",
            promo_id="promo_1",
            cta_text="Click 3",
        )
        await store.log_click(
            user_id="user_4",
            promo_id="promo_2",
            cta_text="Click 4",
        )

        # Retrieve promo's clicks
        clicks = await store.get_promo_clicks(promo_id="promo_1")

        assert len(clicks) == 3
        assert all(click["promo_id"] == "promo_1" for click in clicks)
        assert {click["user_id"] for click in clicks} == {"user_1", "user_2", "user_3"}

    @pytest.mark.asyncio
    async def test_get_click_count(self, db_session):
        """Test getting total click count."""
        store = ClicksStore(db_session=db_session)

        # Log 3 clicks for the promo
        for i in range(3):
            await store.log_click(
                user_id=f"user_{i}",
                promo_id="promo_1",
                cta_text=f"Click {i}",
            )

        count = await store.get_click_count(promo_id="promo_1")

        assert count == 3

    @pytest.mark.asyncio
    async def test_get_conversion_rate(self, db_session):
        """Test calculating conversion rate."""
        store = ClicksStore(db_session=db_session)

        # Log 5 clicks: 2 completed conversions = 40% rate
        await store.log_click(
            user_id="user_1",
            promo_id="promo_1",
            cta_text="Click 1",
            metadata={"conversion": "completed"},
        )
        await store.log_click(
            user_id="user_2",
            promo_id="promo_1",
            cta_text="Click 2",
            metadata={"conversion": "pending"},
        )
        await store.log_click(
            user_id="user_3",
            promo_id="promo_1",
            cta_text="Click 3",
            metadata={"conversion": "completed"},
        )
        await store.log_click(
            user_id="user_4",
            promo_id="promo_1",
            cta_text="Click 4",
            metadata={},
        )
        await store.log_click(
            user_id="user_5",
            promo_id="promo_1",
            cta_text="Click 5",
        )

        rate = await store.get_conversion_rate(promo_id="promo_1")

        assert rate == 40.0  # 2 out of 5

    @pytest.mark.asyncio
    async def test_update_click_metadata(self, db_session):
        """Test updating click metadata."""
        store = ClicksStore(db_session=db_session)

        # Log a click
        click_id = await store.log_click(
            user_id="user_1",
            promo_id="promo_1",
            cta_text="Click 1",
            metadata={"status": "pending"},
        )

        # Update metadata
        await store.update_click_metadata(
            click_id=click_id,
            metadata={"conversion": "completed"},
        )

        # Verify metadata was updated
        clicks = await store.get_user_clicks(user_id="user_1")
        assert len(clicks) == 1
        assert clicks[0]["metadata"]["status"] == "pending"
        assert clicks[0]["metadata"]["conversion"] == "completed"
