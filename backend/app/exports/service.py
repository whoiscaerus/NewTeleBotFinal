"""
PR-057: Export Service

Business logic for generating trade history exports with PII redaction.
"""

import csv
import logging
import secrets
from datetime import datetime, timedelta
from io import StringIO
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.exports.models import ExportToken
from backend.app.trading.store.models import Trade

logger = logging.getLogger(__name__)


class ExportService:
    """Service for generating and managing trade history exports."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_export(
        self, user_id: str, format: str, redact_pii: bool = False
    ) -> dict[str, Any]:
        """Generate trade history export for a user.

        Args:
            user_id: User ID to export trades for
            format: Export format ('csv' or 'json')
            redact_pii: Whether to redact personally identifiable information

        Returns:
            Dict with export data:
            - format: Export format
            - data: Export content (string for CSV, dict for JSON)
            - trade_count: Number of trades exported
            - redacted: Whether PII was redacted

        Raises:
            ValueError: If format is invalid or no trades found
        """
        try:
            # Validate format
            if format not in ["csv", "json"]:
                raise ValueError(f"Invalid format: {format}. Must be 'csv' or 'json'")

            logger.info(
                f"Generating {format} export for user {user_id} (redact_pii={redact_pii})"
            )

            # Fetch user's trades
            stmt = (
                select(Trade)
                .where(Trade.user_id == user_id)
                .order_by(Trade.entry_time.desc())
            )
            result = await self.db.execute(stmt)
            trades = result.scalars().all()

            if not trades:
                raise ValueError(f"No trades found for user {user_id}")

            # Convert trades to dict format
            trade_data = []
            for idx, trade in enumerate(trades, 1):
                trade_dict = {
                    "trade_id": trade.trade_id if not redact_pii else f"TRADE_{idx}",
                    "symbol": trade.symbol,
                    "strategy": trade.strategy,
                    "timeframe": trade.timeframe,
                    "trade_type": trade.trade_type,
                    "volume": float(trade.volume),
                    "entry_price": float(trade.entry_price),
                    "exit_price": float(trade.exit_price) if trade.exit_price else None,
                    "stop_loss": float(trade.stop_loss),
                    "take_profit": float(trade.take_profit),
                    "profit": float(trade.profit) if trade.profit else None,
                    "status": trade.status,
                    "entry_time": trade.entry_time.isoformat(),
                    "exit_time": (
                        trade.exit_time.isoformat() if trade.exit_time else None
                    ),
                }

                # Redact PII if requested
                if redact_pii:
                    # Remove MT5 ticket (could link to real account)
                    trade_dict.pop("mt5_ticket", None)
                    # Remove signal_id and device_id (user-specific)
                    trade_dict.pop("signal_id", None)
                    trade_dict.pop("device_id", None)

                trade_data.append(trade_dict)

            # Generate export in requested format
            data: str | dict[str, Any]
            if format == "csv":
                output = StringIO()
                if trade_data:
                    writer = csv.DictWriter(output, fieldnames=trade_data[0].keys())
                    writer.writeheader()
                    writer.writerows(trade_data)
                data = output.getvalue()
            else:  # json
                data = {
                    "export_date": datetime.utcnow().isoformat(),
                    "trade_count": len(trade_data),
                    "redacted": redact_pii,
                    "trades": trade_data,
                }

            logger.info(
                f"Export generated: {len(trade_data)} trades, format={format}, redacted={redact_pii}"
            )

            return {
                "format": format,
                "data": data,
                "trade_count": len(trade_data),
                "redacted": redact_pii,
            }

        except ValueError:
            raise
        except Exception as e:
            logger.error(
                f"Error generating export for user {user_id}: {e}", exc_info=True
            )
            raise ValueError(f"Failed to generate export: {e}")

    async def create_share_token(
        self,
        user_id: str,
        format: str,
        expires_in_hours: int = 24,
        max_accesses: int = 1,
    ) -> ExportToken:
        """Create a public share token for user's trade history.

        Args:
            user_id: User ID
            format: Export format ('csv' or 'json')
            expires_in_hours: Token expiration time in hours (default 24)
            max_accesses: Maximum number of accesses allowed (default 1 for single-use)

        Returns:
            ExportToken object

        Raises:
            ValueError: If format is invalid
        """
        try:
            # Validate format
            if format not in ["csv", "json"]:
                raise ValueError(f"Invalid format: {format}")

            # Generate secure token (32 bytes = 64 hex chars)
            token = secrets.token_urlsafe(32)

            # Calculate expiration
            expires_at = datetime.utcnow() + timedelta(hours=expires_in_hours)

            # Create token record
            export_token = ExportToken(
                id=str(uuid4()),
                user_id=user_id,
                token=token,
                format=format,
                expires_at=expires_at,
                max_accesses=max_accesses,
                accessed_count=0,
                revoked=False,
            )

            self.db.add(export_token)
            await self.db.commit()
            await self.db.refresh(export_token)

            logger.info(
                f"Created share token for user {user_id}: {token[:8]}... "
                f"(expires={expires_at}, max_accesses={max_accesses})"
            )

            return export_token

        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Error creating share token: {e}", exc_info=True)
            raise ValueError(f"Failed to create share token: {e}")

    async def get_token_by_value(self, token: str) -> ExportToken | None:
        """Retrieve export token by its value.

        Args:
            token: Token string

        Returns:
            ExportToken if found, None otherwise
        """
        try:
            stmt = select(ExportToken).where(ExportToken.token == token)
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching token: {e}", exc_info=True)
            return None

    async def mark_token_accessed(self, token: ExportToken) -> None:
        """Mark token as accessed and update access count.

        Args:
            token: ExportToken to update
        """
        try:
            token.accessed_count += 1
            token.last_accessed_at = datetime.utcnow()
            await self.db.commit()

            logger.info(
                f"Token {token.token[:8]}... accessed "
                f"({token.accessed_count}/{token.max_accesses})"
            )
        except Exception as e:
            logger.error(f"Error marking token accessed: {e}", exc_info=True)
            raise

    async def revoke_token(self, token: ExportToken) -> None:
        """Revoke a share token.

        Args:
            token: ExportToken to revoke
        """
        try:
            token.revoked = True
            await self.db.commit()

            logger.info(f"Token {token.token[:8]}... revoked")
        except Exception as e:
            logger.error(f"Error revoking token: {e}", exc_info=True)
            raise
