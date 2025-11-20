"""
Auto-Trace Queue & Tracer: Manages trade queueing and PII stripping.

Responsibilities:
- Queue management (enqueue, retrieve pending)
- Delay enforcement (T+X calculation)
- PII stripping before posting
- Retry scheduling with backoff
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, cast

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class TraceQueue:
    """
    Manages trace queue for posting trades to external trackers.

    Uses Redis for fast, durable queue storage.
    Tracks: trade_id, deadline, adapter_types, retry_count
    """

    def __init__(self, redis_client: redis.Redis):
        """Initialize queue with Redis client."""
        self.redis = redis_client
        self.queue_prefix = "trace_queue:"
        self.pending_key = "trace_pending"  # Sorted set by deadline

    async def enqueue_closed_trade(
        self, trade_id: str, adapter_types: list[str], delay_minutes: int = 5
    ) -> None:
        """
        Enqueue a closed trade for posting.

        Args:
            trade_id: Trade ID to queue
            adapter_types: List of adapters to post to (e.g., ["myfxbook", "file_export"])
            delay_minutes: Delay before posting (default 5 minutes)

        Stores:
        {
            "trade_id": "...",
            "adapter_types": ["myfxbook", "file_export"],
            "deadline": "2025-01-15T11:05:00Z",
            "retry_count": 0,
            "created_at": "2025-01-15T11:00:00Z"
        }
        """
        try:
            now = datetime.utcnow()
            deadline = now + timedelta(minutes=delay_minutes)

            queue_entry: dict[str, str | int] = {
                "trade_id": trade_id,
                "adapter_types": json.dumps(adapter_types),
                "deadline": deadline.isoformat() + "Z",
                "retry_count": 0,
                "created_at": now.isoformat() + "Z",
            }

            # Store in Redis hash
            key = f"{self.queue_prefix}{trade_id}"
            await self.redis.hset(key, mapping=cast(Any, queue_entry))

            # Add to sorted set for efficient deadline lookup
            deadline_score = deadline.timestamp()
            await self.redis.zadd(self.pending_key, {key: deadline_score})

            # Set TTL: 7 days (if processing takes that long, something is wrong)
            await self.redis.expire(key, 7 * 24 * 3600)

            logger.info(
                f"Trade queued for tracing: {trade_id}",
                extra={
                    "trade_id": trade_id,
                    "deadline": deadline.isoformat(),
                    "adapters": adapter_types,
                    "delay_minutes": delay_minutes,
                },
            )

        except Exception as e:
            logger.error(
                f"Failed to enqueue trade: {str(e)}",
                extra={"trade_id": trade_id, "error": str(e)},
                exc_info=True,
            )
            raise

    async def get_pending_traces(self, batch_size: int = 10) -> list[dict[str, Any]]:
        """
        Fetch all traces ready to post (deadline < now).

        Args:
            batch_size: Maximum traces to fetch

        Returns:
            List of {trade_id, adapters, deadline, retry_count}
        """
        try:
            now = datetime.utcnow()
            deadline_score = now.timestamp()

            # Get keys with deadline <= now (sorted set)
            keys = await self.redis.zrangebyscore(
                self.pending_key,
                min="-inf",
                max=deadline_score,
                start=0,
                num=batch_size,
            )

            pending = []
            for key in keys:
                # Decode key (Redis returns bytes)
                if isinstance(key, bytes):
                    key = key.decode("utf-8")

                # Get full trace entry
                trace_data = await self.redis.hgetall(key)

                if trace_data:
                    # Decode Redis bytes
                    trace = {
                        k.decode("utf-8") if isinstance(k, bytes) else k: (
                            v.decode("utf-8") if isinstance(v, bytes) else v
                        )
                        for k, v in trace_data.items()
                    }

                    # Parse adapter types
                    trade_id = trace.get("trade_id")
                    adapter_str = trace.get("adapter_types", "[]")
                    adapters = json.loads(adapter_str)

                    pending.append(
                        {
                            "trace_key": key,
                            "trade_id": trade_id,
                            "adapters": adapters,
                            "deadline": trace.get("deadline"),
                            "retry_count": int(trace.get("retry_count", 0)),
                        }
                    )

            if pending:
                logger.info(
                    f"Found {len(pending)} pending traces ready for posting",
                    extra={"count": len(pending), "batch_size": batch_size},
                )

            return pending

        except Exception as e:
            logger.error(
                f"Failed to get pending traces: {str(e)}",
                extra={"error": str(e)},
                exc_info=True,
            )
            return []

    async def mark_success(self, trace_key: str) -> None:
        """
        Delete from queue after successful post.

        Args:
            trace_key: Redis key from pending trace
        """
        try:
            # Remove from sorted set
            await self.redis.zrem(self.pending_key, trace_key)

            # Delete hash
            await self.redis.delete(trace_key)

            logger.debug(f"Trace marked as success and deleted: {trace_key}")

        except Exception as e:
            logger.error(
                f"Failed to mark trace success: {str(e)}",
                extra={"trace_key": trace_key, "error": str(e)},
                exc_info=True,
            )

    async def schedule_retry(
        self, trace_key: str, retry_count: int, backoff_seconds: int
    ) -> None:
        """
        Schedule retry with exponential backoff.

        Args:
            trace_key: Redis key from pending trace
            retry_count: Current retry number (0-4)
            backoff_seconds: Seconds to wait before retry
        """
        try:
            # Update retry count
            await self.redis.hincrby(trace_key, "retry_count", 1)

            # Calculate new deadline
            new_deadline = datetime.utcnow() + timedelta(seconds=backoff_seconds)
            deadline_score = new_deadline.timestamp()

            # Update sorted set score
            await self.redis.zadd(self.pending_key, {trace_key: deadline_score})

            logger.info(
                f"Retry scheduled with {backoff_seconds}s backoff",
                extra={
                    "trace_key": trace_key,
                    "retry_count": retry_count + 1,
                    "backoff_seconds": backoff_seconds,
                    "new_deadline": new_deadline.isoformat(),
                },
            )

        except Exception as e:
            logger.error(
                f"Failed to schedule retry: {str(e)}",
                extra={"trace_key": trace_key, "error": str(e)},
                exc_info=True,
            )

    async def abandon_after_max_retries(
        self, trace_key: str, max_retries: int = 5
    ) -> None:
        """
        Give up on trace after max retries exceeded.

        Args:
            trace_key: Redis key
            max_retries: Maximum retry attempts (default 5)
        """
        try:
            # Get current retry count
            trace_data = await self.redis.hgetall(trace_key)
            retry_count = int(trace_data.get(b"retry_count", 0))
            trade_id = trace_data.get(b"trade_id", b"unknown").decode("utf-8")

            # Delete from queue
            await self.redis.zrem(self.pending_key, trace_key)
            await self.redis.delete(trace_key)

            logger.error(
                f"Trace abandoned after {retry_count} retries",
                extra={
                    "trace_key": trace_key,
                    "trade_id": trade_id,
                    "retry_count": retry_count,
                    "max_retries": max_retries,
                },
            )

        except Exception as e:
            logger.error(
                f"Failed to abandon trace: {str(e)}",
                extra={"trace_key": trace_key, "error": str(e)},
                exc_info=True,
            )


async def strip_pii_from_trade(trade: Any) -> dict[str, Any]:
    """
    Strip personally identifiable information from trade.

    Removed fields:
    - user_id, user.email, user.name, user.phone
    - client_id, account_id, account_name
    - broker_account_number
    - Any custom metadata with user data

    Kept fields:
    - trade_id (anonymized if needed)
    - instrument, side, entry/exit prices
    - volume, entry/exit times
    - profit/loss calculations
    - signal_id (non-PII)

    Args:
        trade: Trade ORM object

    Returns:
        Dict with PII stripped, safe for external posting
    """
    try:
        # Build safe trade dict
        safe_trade = {
            "trade_id": str(trade.id),
            "signal_id": str(trade.signal_id) if trade.signal_id else None,
            "instrument": trade.instrument,
            "side": "buy" if trade.side == 0 else "sell",  # Assuming 0=buy, 1=sell
            "volume": float(trade.volume) if trade.volume else 0.0,
            "entry_price": float(trade.entry_price) if trade.entry_price else 0.0,
            "exit_price": float(trade.exit_price) if trade.exit_price else 0.0,
            "stop_loss": (
                float(trade.stop_loss)
                if hasattr(trade, "stop_loss") and trade.stop_loss
                else None
            ),
            "take_profit": (
                float(trade.take_profit)
                if hasattr(trade, "take_profit") and trade.take_profit
                else None
            ),
            "entry_time": (
                trade.entry_time.isoformat() + "Z" if trade.entry_time else None
            ),
            "exit_time": trade.exit_time.isoformat() + "Z" if trade.exit_time else None,
            "profit_loss": (
                float(trade.profit_loss)
                if hasattr(trade, "profit_loss") and trade.profit_loss
                else 0.0
            ),
            "profit_loss_percent": (
                float(trade.profit_loss_pct)
                if hasattr(trade, "profit_loss_pct") and trade.profit_loss_pct
                else 0.0
            ),
            "status": getattr(trade, "status", "closed"),
        }

        logger.debug(
            f"PII stripped from trade: {trade.id}",
            extra={"trade_id": str(trade.id), "fields_kept": len(safe_trade)},
        )

        return safe_trade

    except Exception as e:
        logger.error(
            f"Failed to strip PII from trade: {str(e)}",
            extra={"trade_id": getattr(trade, "id", "unknown"), "error": str(e)},
            exc_info=True,
        )
        raise


async def get_trace_queue(redis_client: redis.Redis) -> TraceQueue:
    """Factory function to get trace queue instance."""
    return TraceQueue(redis_client)
