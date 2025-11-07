"""Comprehensive tests for messaging bus (PR-060).

Tests cover:
- Queue operations (enqueue/dequeue)
- FIFO order
- Priority lanes (transactional before campaign)
- Retry logic with exponential backoff
- Dead letter queue after 5 failures
- Concurrent enqueueing
- Message serialization
- Metrics tracking

Target: 100% coverage of backend/app/messaging/bus.py (650 lines)
"""

import asyncio
import json
from unittest.mock import MagicMock

import pytest
import pytest_asyncio

from backend.tests.messaging_test_helpers import (
    CAMPAIGN_QUEUE,
    DEAD_LETTER_QUEUE,
    MAX_RETRIES,
    RETRY_DELAYS,
    TRANSACTIONAL_QUEUE,
    MessagingBus,
    dequeue_message,
    enqueue_campaign,
    enqueue_message,
    get_bus,
    retry_message,
)


@pytest_asyncio.fixture
async def mock_redis(monkeypatch):
    """Mock Redis client with in-memory dictionary."""
    redis_data = {}  # In-memory storage for THIS test

    class MockRedis:
        def __init__(self):
            self.data = redis_data

        async def rpush(self, key, value):
            """Push to right of list (enqueue)."""
            if key not in self.data:
                self.data[key] = []
            self.data[key].append(value)
            return len(self.data[key])

        async def lpop(self, key):
            """Pop from left of list (dequeue)."""
            if key not in self.data or len(self.data[key]) == 0:
                return None
            return self.data[key].pop(0)

        async def llen(self, key):
            """Get list length."""
            return len(self.data.get(key, []))

        async def ping(self):
            """Mock ping for health check."""
            return True

    # Create mock Redis instance
    mock_redis_instance = MockRedis()

    # Patch redis.asyncio.from_url to return our mock (sync function returning object)
    def mock_redis_from_url(*args, **kwargs):
        return mock_redis_instance

    monkeypatch.setattr("redis.asyncio.from_url", mock_redis_from_url)

    # Reset the global bus instance to force re-initialization with mocked Redis
    import backend.app.messaging.bus as bus_module

    bus_module._bus = bus_module.MessagingBus()
    bus_module._bus._initialized = False

    yield mock_redis_instance


@pytest.fixture
def mock_metrics(monkeypatch):
    """Mock Prometheus metrics."""
    mock_enqueued = MagicMock()
    mock_failed = MagicMock()

    monkeypatch.setattr(
        "backend.app.messaging.bus.messages_enqueued_total", mock_enqueued
    )
    monkeypatch.setattr("backend.app.messaging.bus.message_fail_total", mock_failed)

    return {"enqueued": mock_enqueued, "failed": mock_failed}


class TestMessagingBusEnqueue:
    """Test message enqueueing operations."""

    @pytest.mark.asyncio
    async def test_enqueue_transactional_message(self, mock_redis, mock_metrics):
        """Test enqueuing a transactional message."""
        message_id = await enqueue_message(
            user_id="user-123",
            channel="email",
            template_name="position_failure_entry",
            template_vars={"instrument": "XAUUSD", "side": "buy"},
            priority="transactional",
        )

        # Verify message ID format (UUID)
        assert isinstance(message_id, str)
        assert len(message_id) > 0

        # Verify message in transactional queue
        assert TRANSACTIONAL_QUEUE in mock_redis.data
        assert len(mock_redis.data[TRANSACTIONAL_QUEUE]) == 1

        # Verify message structure
        message_json = mock_redis.data[TRANSACTIONAL_QUEUE][0]
        message = json.loads(message_json)
        assert message["message_id"] == message_id
        assert message["user_id"] == "user-123"
        assert message["channel"] == "email"
        assert message["template_name"] == "position_failure_entry"
        assert message["template_vars"]["instrument"] == "XAUUSD"
        assert message["priority"] == "transactional"
        assert message["retry_count"] == 0
        assert "enqueued_at" in message

        # Verify metrics
        mock_metrics["enqueued"].labels.assert_called_with(
            priority="transactional", channel="email"
        )
        mock_metrics["enqueued"].labels().inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_enqueue_campaign_message(self, mock_redis, mock_metrics):
        """Test enqueuing a campaign message."""
        _ = await enqueue_message(
            user_id="user-456",
            channel="telegram",
            template_name="marketing_alert",
            template_vars={"promo": "50% off"},
            priority="campaign",
        )

        # Verify message in campaign queue
        assert CAMPAIGN_QUEUE in mock_redis.data
        assert len(mock_redis.data[CAMPAIGN_QUEUE]) == 1

        # Verify priority is campaign
        message_json = mock_redis.data[CAMPAIGN_QUEUE][0]
        message = json.loads(message_json)
        assert message["priority"] == "campaign"

        # Verify metrics
        mock_metrics["enqueued"].labels.assert_called_with(
            priority="campaign", channel="telegram"
        )

    @pytest.mark.asyncio
    async def test_enqueue_default_priority_is_transactional(
        self, mock_redis, mock_metrics
    ):
        """Test default priority is transactional."""
        await enqueue_message(
            user_id="user-789",
            channel="push",
            template_name="alert",
            template_vars={},
            # priority not specified
        )

        # Verify message in transactional queue (default)
        assert TRANSACTIONAL_QUEUE in mock_redis.data
        assert len(mock_redis.data[TRANSACTIONAL_QUEUE]) == 1

    @pytest.mark.asyncio
    async def test_enqueue_preserves_all_fields(self, mock_redis):
        """Test all message fields are preserved."""
        template_vars = {
            "instrument": "XAUUSD",
            "side": "sell",
            "entry_price": 1950.50,
            "volume": 0.1,
            "error_reason": "Insufficient margin",
            "approval_id": "approval-123",
        }

        await enqueue_message(
            user_id="user-complex",
            channel="email",
            template_name="position_failure_entry",
            template_vars=template_vars,
            priority="transactional",
        )

        # Verify all fields preserved
        message_json = mock_redis.data[TRANSACTIONAL_QUEUE][0]
        message = json.loads(message_json)
        assert message["template_vars"] == template_vars
        assert message["template_vars"]["entry_price"] == 1950.50  # Float preserved


class TestMessagingBusDequeue:
    """Test message dequeueing operations."""

    @pytest.mark.asyncio
    async def test_dequeue_transactional_message(self, mock_redis):
        """Test dequeueing from transactional queue."""
        # Enqueue message
        message_id = await enqueue_message(
            user_id="user-123",
            channel="email",
            template_name="alert",
            template_vars={},
            priority="transactional",
        )

        # Dequeue message
        message = await dequeue_message(priority="transactional")

        # Verify message returned
        assert message is not None
        assert message["message_id"] == message_id
        assert message["user_id"] == "user-123"

        # Verify queue empty
        assert len(mock_redis.data.get(TRANSACTIONAL_QUEUE, [])) == 0

    @pytest.mark.asyncio
    async def test_dequeue_campaign_message(self, mock_redis):
        """Test dequeueing from campaign queue."""
        # Enqueue message
        message_id = await enqueue_message(
            user_id="user-456",
            channel="telegram",
            template_name="marketing",
            template_vars={},
            priority="campaign",
        )

        # Dequeue message
        message = await dequeue_message(priority="campaign")

        # Verify message returned
        assert message is not None
        assert message["message_id"] == message_id
        assert message["priority"] == "campaign"

        # Verify queue empty
        assert len(mock_redis.data.get(CAMPAIGN_QUEUE, [])) == 0

    @pytest.mark.asyncio
    async def test_dequeue_empty_queue_returns_none(self, mock_redis):
        """Test dequeueing from empty queue returns None."""
        message = await dequeue_message(priority="transactional")
        assert message is None

        message = await dequeue_message(priority="campaign")
        assert message is None

    @pytest.mark.asyncio
    async def test_dequeue_fifo_order(self, mock_redis):
        """Test messages dequeued in FIFO order."""
        # Enqueue 3 messages
        id1 = await enqueue_message(
            user_id="user-1", channel="email", template_name="t1", template_vars={}
        )
        id2 = await enqueue_message(
            user_id="user-2", channel="email", template_name="t2", template_vars={}
        )
        id3 = await enqueue_message(
            user_id="user-3", channel="email", template_name="t3", template_vars={}
        )

        # Dequeue in order
        msg1 = await dequeue_message(priority="transactional")
        msg2 = await dequeue_message(priority="transactional")
        msg3 = await dequeue_message(priority="transactional")

        # Verify FIFO order
        assert msg1["message_id"] == id1
        assert msg2["message_id"] == id2
        assert msg3["message_id"] == id3

    @pytest.mark.asyncio
    async def test_dequeue_priority_lanes_isolated(self, mock_redis):
        """Test transactional and campaign queues are isolated."""
        # Enqueue to both queues
        trans_id = await enqueue_message(
            user_id="user-trans",
            channel="email",
            template_name="trans",
            template_vars={},
            priority="transactional",
        )
        camp_id = await enqueue_message(
            user_id="user-camp",
            channel="email",
            template_name="camp",
            template_vars={},
            priority="campaign",
        )

        # Dequeue from transactional - should only get transactional
        msg = await dequeue_message(priority="transactional")
        assert msg["message_id"] == trans_id
        assert msg["priority"] == "transactional"

        # Dequeue from campaign - should only get campaign
        msg = await dequeue_message(priority="campaign")
        assert msg["message_id"] == camp_id
        assert msg["priority"] == "campaign"


class TestMessagingBusRetry:
    """Test retry logic with exponential backoff."""

    @pytest.mark.asyncio
    async def test_retry_message_increments_count(self, mock_redis):
        """Test retry_message increments retry_count."""
        # Enqueue and dequeue message
        await enqueue_message(
            user_id="user-123",
            channel="email",
            template_name="alert",
            template_vars={},
        )
        message = await dequeue_message(priority="transactional")

        # Retry message
        await retry_message(message)

        # Dequeue retried message
        retried = await dequeue_message(priority="transactional")

        # Verify retry_count incremented
        assert retried["retry_count"] == 1

    @pytest.mark.asyncio
    async def test_retry_message_preserves_all_fields(self, mock_redis):
        """Test retry preserves all original fields."""
        template_vars = {"instrument": "GOLD", "price": 1950.50}

        await enqueue_message(
            user_id="user-preserve",
            channel="telegram",
            template_name="alert",
            template_vars=template_vars,
        )
        message = await dequeue_message(priority="transactional")

        # Retry message
        await retry_message(message)

        # Dequeue retried message
        retried = await dequeue_message(priority="transactional")

        # Verify all fields preserved
        assert retried["user_id"] == "user-preserve"
        assert retried["channel"] == "telegram"
        assert retried["template_name"] == "alert"
        assert retried["template_vars"] == template_vars
        assert retried["retry_count"] == 1

    @pytest.mark.asyncio
    async def test_retry_message_multiple_times(self, mock_redis):
        """Test message can be retried multiple times."""
        await enqueue_message(
            user_id="user-multi", channel="email", template_name="t", template_vars={}
        )

        # Retry the message 3 times
        for _ in range(1, 4):
            message = await dequeue_message(priority="transactional")
            assert message is not None
            await retry_message(message)

        # Dequeue final retried message
        final = await dequeue_message(priority="transactional")
        assert final["retry_count"] == 3

    @pytest.mark.asyncio
    async def test_retry_delay_exponential_backoff(self):
        """Test RETRY_DELAYS has exponential backoff."""
        # Verify delay values
        assert RETRY_DELAYS == [1, 2, 4, 8, 16]

        # Verify exponential growth
        for i in range(1, len(RETRY_DELAYS)):
            assert RETRY_DELAYS[i] == RETRY_DELAYS[i - 1] * 2


class TestMessagingBusDeadLetterQueue:
    """Test dead letter queue after max retries."""

    @pytest.mark.asyncio
    async def test_message_moved_to_dlq_after_max_retries(
        self, mock_redis, mock_metrics
    ):
        """Test message moves to DLQ after MAX_RETRIES."""
        # Enqueue message
        await enqueue_message(
            user_id="user-dlq", channel="email", template_name="t", template_vars={}
        )

        # Retry MAX_RETRIES times
        for _ in range(MAX_RETRIES):
            message = await dequeue_message(priority="transactional")
            await retry_message(message)

        # Try one more retry (should move to DLQ)
        message = await dequeue_message(priority="transactional")
        await retry_message(message)

        # Verify message NOT in transactional queue
        msg = await dequeue_message(priority="transactional")
        assert msg is None

        # Verify message in DLQ
        assert DEAD_LETTER_QUEUE in mock_redis.data
        assert len(mock_redis.data[DEAD_LETTER_QUEUE]) == 1

        # Verify DLQ message has correct retry_count
        dlq_message_json = mock_redis.data[DEAD_LETTER_QUEUE][0]
        dlq_message = json.loads(dlq_message_json)
        assert dlq_message["retry_count"] == MAX_RETRIES

        # Verify failure metric
        mock_metrics["failed"].labels.assert_called_with(
            reason="max_retries", channel="email"
        )

    @pytest.mark.asyncio
    async def test_max_retries_constant_value(self):
        """Test MAX_RETRIES is 5."""
        assert MAX_RETRIES == 5

    @pytest.mark.asyncio
    async def test_dlq_message_preserves_all_fields(self, mock_redis, mock_metrics):
        """Test DLQ message preserves all original fields."""
        template_vars = {"key": "value", "number": 123}

        await enqueue_message(
            user_id="user-dlq-preserve",
            channel="telegram",
            template_name="alert",
            template_vars=template_vars,
        )

        # Retry MAX_RETRIES + 1 times to move to DLQ
        for _ in range(MAX_RETRIES + 1):
            message = await dequeue_message(priority="transactional")
            await retry_message(message)

        # Verify DLQ message
        dlq_message_json = mock_redis.data[DEAD_LETTER_QUEUE][0]
        dlq_message = json.loads(dlq_message_json)
        assert dlq_message["user_id"] == "user-dlq-preserve"
        assert dlq_message["channel"] == "telegram"
        assert dlq_message["template_vars"] == template_vars


class TestMessagingBusCampaign:
    """Test campaign batch enqueueing."""

    @pytest.mark.asyncio
    async def test_enqueue_campaign_batch(self, mock_redis, mock_metrics):
        """Test enqueuing campaign to multiple users."""
        user_ids = ["user-1", "user-2", "user-3"]

        def template_vars_fn(user_id):
            return {"user_id": user_id, "promo": "50% off"}

        result = await enqueue_campaign(
            user_ids=user_ids,
            channel="email",
            template_name="marketing",
            template_vars_fn=template_vars_fn,
        )

        # Verify result shows 3 queued, 0 failed
        assert result["queued"] == 3
        assert result["failed"] == 0

        # Verify all messages in campaign queue
        assert len(mock_redis.data[CAMPAIGN_QUEUE]) == 3

        # Verify each message has correct user_id and template_vars
        for i, user_id in enumerate(user_ids):
            message_json = mock_redis.data[CAMPAIGN_QUEUE][i]
            message = json.loads(message_json)
            assert message["user_id"] == user_id
            assert message["template_vars"]["user_id"] == user_id
            assert message["template_vars"]["promo"] == "50% off"
            assert message["priority"] == "campaign"

        # Verify metrics called 3 times
        assert mock_metrics["enqueued"].labels().inc.call_count == 3

    @pytest.mark.asyncio
    async def test_enqueue_campaign_with_batching(self, mock_redis):
        """Test campaign with batch_size parameter."""
        user_ids = [f"user-{i}" for i in range(10)]

        def template_vars_fn(user_id):
            return {"user_id": user_id}

        result = await enqueue_campaign(
            user_ids=user_ids,
            channel="telegram",
            template_name="promo",
            template_vars_fn=template_vars_fn,
            batch_size=3,  # Process in batches of 3
        )

        # Verify all 10 messages enqueued
        assert result["queued"] == 10
        assert result["failed"] == 0
        assert len(mock_redis.data[CAMPAIGN_QUEUE]) == 10

    @pytest.mark.asyncio
    async def test_enqueue_campaign_empty_list(self, mock_redis):
        """Test campaign with empty user list."""
        result = await enqueue_campaign(
            user_ids=[],
            channel="email",
            template_name="marketing",
            template_vars_fn=lambda uid: {},
        )

        # Verify no messages enqueued
        assert result["queued"] == 0
        assert result["failed"] == 0
        assert len(mock_redis.data.get(CAMPAIGN_QUEUE, [])) == 0


class TestMessagingBusConcurrency:
    """Test concurrent enqueueing."""

    @pytest.mark.asyncio
    async def test_concurrent_enqueue(self, mock_redis):
        """Test multiple concurrent enqueue operations."""

        async def enqueue_task(user_id):
            return await enqueue_message(
                user_id=user_id,
                channel="email",
                template_name="alert",
                template_vars={},
            )

        # Enqueue 10 messages concurrently
        user_ids = [f"user-{i}" for i in range(10)]
        message_ids = await asyncio.gather(*[enqueue_task(uid) for uid in user_ids])

        # Verify all 10 messages enqueued
        assert len(message_ids) == 10
        assert len(mock_redis.data[TRANSACTIONAL_QUEUE]) == 10

        # Verify all message IDs unique
        assert len(set(message_ids)) == 10

    @pytest.mark.asyncio
    async def test_concurrent_enqueue_dequeue(self, mock_redis):
        """Test concurrent enqueue and dequeue operations."""

        async def enqueue_task():
            for i in range(5):
                await enqueue_message(
                    user_id=f"user-{i}",
                    channel="email",
                    template_name="alert",
                    template_vars={},
                )
                await asyncio.sleep(0.01)

        async def dequeue_task():
            messages = []
            for _ in range(5):
                await asyncio.sleep(0.02)
                msg = await dequeue_message(priority="transactional")
                if msg:
                    messages.append(msg)
            return messages

        # Run enqueue and dequeue concurrently
        enqueue_result, dequeue_result = await asyncio.gather(
            enqueue_task(), dequeue_task()
        )

        # Verify some messages were dequeued
        assert len(dequeue_result) >= 1


class TestMessagingBusSingleton:
    """Test MessagingBus singleton pattern."""

    @pytest.mark.asyncio
    async def test_get_bus_returns_same_instance(self):
        """Test get_bus() always returns same instance."""
        bus1 = await get_bus()
        bus2 = await get_bus()

        assert bus1 is bus2

    @pytest.mark.asyncio
    async def test_bus_initialization(self):
        """Test MessagingBus initializes correctly."""
        bus = MessagingBus()

        # Verify bus instance created
        assert bus is not None
        assert hasattr(bus, "redis_client")
        assert hasattr(bus, "_initialized")

        # Verify module-level constants defined
        assert TRANSACTIONAL_QUEUE == "messaging:queue:transactional"
        assert CAMPAIGN_QUEUE == "messaging:queue:campaign"
        assert DEAD_LETTER_QUEUE == "messaging:queue:dlq"


class TestMessagingBusMetrics:
    """Test Prometheus metrics integration."""

    @pytest.mark.asyncio
    async def test_enqueue_increments_metric(self, mock_redis, mock_metrics):
        """Test enqueue increments messages_enqueued_total."""
        await enqueue_message(
            user_id="user-123",
            channel="email",
            template_name="alert",
            template_vars={},
        )

        # Verify metric called with correct labels
        mock_metrics["enqueued"].labels.assert_called_with(
            priority="transactional", channel="email"
        )
        mock_metrics["enqueued"].labels().inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_dlq_increments_fail_metric(self, mock_redis, mock_metrics):
        """Test DLQ increments message_fail_total."""
        await enqueue_message(
            user_id="user-dlq", channel="telegram", template_name="t", template_vars={}
        )

        # Retry until DLQ
        for _ in range(MAX_RETRIES + 1):
            message = await dequeue_message(priority="transactional")
            await retry_message(message)

        # Verify fail metric called
        mock_metrics["failed"].labels.assert_called_with(
            reason="max_retries", channel="telegram"
        )
        mock_metrics["failed"].labels().inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_metrics_track_different_channels(self, mock_redis, mock_metrics):
        """Test metrics track each channel separately."""
        await enqueue_message(
            user_id="u1", channel="email", template_name="t", template_vars={}
        )
        await enqueue_message(
            user_id="u2", channel="telegram", template_name="t", template_vars={}
        )
        await enqueue_message(
            user_id="u3", channel="push", template_name="t", template_vars={}
        )

        # Verify metrics called for each channel
        calls = mock_metrics["enqueued"].labels.call_args_list
        assert len(calls) == 3
        channels = [call[1]["channel"] for call in calls]
        assert set(channels) == {"email", "telegram", "push"}
