"""Data export service for GDPR compliance."""

import csv
import io
import json
import zipfile
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.logging import get_logger
from backend.app.privacy.models import PrivacyRequest, RequestStatus

logger = get_logger(__name__)


class DataExporter:
    """
    Service for exporting user data in GDPR-compliant format.

    Exports include:
    - User profile (no passwords)
    - Trade history (redacted sensitive fields)
    - Billing history (no PCI data)
    - Preferences and settings
    - Audit logs
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def export_user_data(self, user_id: str, request_id: str) -> dict[str, Any]:
        """
        Export all user data to JSON/CSV bundle.

        Args:
            user_id: User ID to export data for
            request_id: Privacy request ID for tracking

        Returns:
            Dict containing export bundle metadata and data

        Raises:
            ValueError: If user not found
        """
        logger.info(f"Starting data export for user {user_id}, request {request_id}")

        try:
            # Collect all user data
            export_data = {
                "export_metadata": {
                    "user_id": user_id,
                    "request_id": request_id,
                    "exported_at": datetime.utcnow().isoformat(),
                    "format_version": "1.0",
                },
                "user_profile": await self._export_user_profile(user_id),
                "trades": await self._export_trades(user_id),
                "billing": await self._export_billing(user_id),
                "preferences": await self._export_preferences(user_id),
                "devices": await self._export_devices(user_id),
                "audit_logs": await self._export_audit_logs(user_id),
            }

            logger.info(f"Data export completed for user {user_id}")
            return export_data

        except Exception as e:
            logger.error(f"Data export failed for user {user_id}: {e}", exc_info=True)
            raise

    async def _export_user_profile(self, user_id: str) -> dict[str, Any]:
        """Export user profile data (no passwords)."""
        from backend.app.auth.models import User

        result = await self.db.execute(select(User).filter(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            raise ValueError(f"User {user_id} not found")

        return {
            "id": user.id,
            "telegram_id": user.telegram_id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": getattr(user, "email", None),
            "phone": getattr(user, "phone", None),
            "is_active": user.is_active,
            "is_premium": user.is_premium,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_seen_at": (
                user.last_seen_at.isoformat()
                if hasattr(user, "last_seen_at") and user.last_seen_at
                else None
            ),
        }

    async def _export_trades(self, user_id: str) -> list[dict[str, Any]]:
        """Export trade history (redact sensitive fields like API keys, internal IDs)."""
        from backend.app.signals.models import Signal

        result = await self.db.execute(
            select(Signal)
            .filter(Signal.user_id == user_id)
            .order_by(Signal.created_at.desc())
        )
        signals = result.scalars().all()

        trades = []
        for signal in signals:
            trades.append(
                {
                    "signal_id": signal.id,
                    "instrument": signal.instrument,
                    "side": "buy" if signal.side == 0 else "sell",
                    "entry_price": (
                        signal.entry_price if hasattr(signal, "entry_price") else None
                    ),
                    "stop_loss": (
                        signal.stop_loss if hasattr(signal, "stop_loss") else None
                    ),
                    "take_profit": (
                        signal.take_profit if hasattr(signal, "take_profit") else None
                    ),
                    "status": (
                        ["new", "approved", "filled", "closed"][signal.status]
                        if hasattr(signal, "status")
                        else "unknown"
                    ),
                    "created_at": (
                        signal.created_at.isoformat() if signal.created_at else None
                    ),
                    "updated_at": (
                        signal.updated_at.isoformat() if signal.updated_at else None
                    ),
                    # Redacted: broker_ticket, device_secret, internal routing IDs
                }
            )

        return trades

    async def _export_billing(self, user_id: str) -> list[dict[str, Any]]:
        """Export billing history (no PCI data like full card numbers)."""
        # Note: In real implementation, query subscription/payment tables
        # For now, return placeholder structure

        billing_records = []

        # Example structure (would query real tables):
        # from backend.app.billing.models import Payment
        # result = await self.db.execute(select(Payment).filter(Payment.user_id == user_id))
        # payments = result.scalars().all()
        # for payment in payments:
        #     billing_records.append({...})

        return billing_records

    async def _export_preferences(self, user_id: str) -> dict[str, Any]:
        """Export user preferences and settings."""
        # Note: In real implementation, query preferences table
        # For now, return placeholder structure

        return {
            "notification_preferences": {},
            "trading_preferences": {},
            "ui_preferences": {},
        }

    async def _export_devices(self, user_id: str) -> list[dict[str, Any]]:
        """Export registered devices (no secrets)."""
        from backend.app.ea.models import Device

        result = await self.db.execute(
            select(Device)
            .filter(Device.user_id == user_id)
            .order_by(Device.created_at.desc())
        )
        devices = result.scalars().all()

        device_list = []
        for device in devices:
            device_list.append(
                {
                    "device_id": device.id,
                    "name": device.name,
                    "is_active": device.is_active,
                    "created_at": (
                        device.created_at.isoformat() if device.created_at else None
                    ),
                    "last_seen_at": (
                        device.last_seen_at.isoformat()
                        if hasattr(device, "last_seen_at") and device.last_seen_at
                        else None
                    ),
                    # Redacted: device_secret
                }
            )

        return device_list

    async def _export_audit_logs(self, user_id: str) -> list[dict[str, Any]]:
        """Export audit trail for user actions."""
        from backend.app.core.audit import AuditLog

        result = await self.db.execute(
            select(AuditLog)
            .filter(AuditLog.user_id == user_id)
            .order_by(AuditLog.timestamp.desc())
            .limit(1000)  # Last 1000 events
        )
        logs = result.scalars().all()

        audit_list = []
        for log in logs:
            audit_list.append(
                {
                    "event_type": log.event_type,
                    "action": log.action,
                    "timestamp": log.timestamp.isoformat() if log.timestamp else None,
                    "metadata": log.metadata if hasattr(log, "metadata") else {},
                }
            )

        return audit_list

    def create_export_bundle(self, export_data: dict[str, Any]) -> bytes:
        """
        Create ZIP bundle with JSON and CSV files.

        Args:
            export_data: Exported data dictionary

        Returns:
            ZIP file bytes
        """
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            # Add JSON export
            json_content = json.dumps(export_data, indent=2, default=str)
            zip_file.writestr("export.json", json_content)

            # Add CSV files for each data type
            if export_data.get("trades"):
                csv_buffer = io.StringIO()
                if export_data["trades"]:
                    writer = csv.DictWriter(
                        csv_buffer, fieldnames=export_data["trades"][0].keys()
                    )
                    writer.writeheader()
                    writer.writerows(export_data["trades"])
                zip_file.writestr("trades.csv", csv_buffer.getvalue())

            if export_data.get("billing"):
                csv_buffer = io.StringIO()
                if export_data["billing"]:
                    writer = csv.DictWriter(
                        csv_buffer, fieldnames=export_data["billing"][0].keys()
                    )
                    writer.writeheader()
                    writer.writerows(export_data["billing"])
                zip_file.writestr("billing.csv", csv_buffer.getvalue())

            if export_data.get("devices"):
                csv_buffer = io.StringIO()
                if export_data["devices"]:
                    writer = csv.DictWriter(
                        csv_buffer, fieldnames=export_data["devices"][0].keys()
                    )
                    writer.writeheader()
                    writer.writerows(export_data["devices"])
                zip_file.writestr("devices.csv", csv_buffer.getvalue())

            # Add README
            readme = """# Your Data Export

This archive contains all your personal data stored in our system.

## Files Included:
- export.json: Complete data in JSON format
- trades.csv: Your trade history
- billing.csv: Your billing history
- devices.csv: Your registered devices

## Data Redaction:
For security, the following fields are redacted:
- Passwords and authentication secrets
- Payment card details (PCI data)
- Internal system identifiers
- Device secrets and API keys

## Questions?
Contact privacy@example.com for assistance.
"""
            zip_file.writestr("README.txt", readme)

        zip_buffer.seek(0)
        return zip_buffer.getvalue()

    async def store_export_bundle(
        self, bundle_bytes: bytes, request: PrivacyRequest, expiry_days: int = 30
    ) -> str:
        """
        Store export bundle in object storage and update request.

        Args:
            bundle_bytes: ZIP file bytes
            request: Privacy request to update
            expiry_days: Days until export URL expires

        Returns:
            URL to download export bundle
        """
        # In production: Upload to S3/GCS/Azure Blob Storage
        # For now: Simulate with local path (would use boto3/storage client)

        filename = f"export_{request.user_id}_{request.id}.zip"

        # Simulate S3 upload
        # storage_client.upload(bucket="privacy-exports", key=filename, body=bundle_bytes)

        # Generate signed URL (would use storage client's presigned_url method)
        export_url = (
            f"https://storage.example.com/privacy-exports/{filename}?token=simulated"
        )

        # Update request with export URL and expiry
        request.export_url = export_url
        request.export_expires_at = datetime.utcnow() + timedelta(days=expiry_days)
        request.status = RequestStatus.COMPLETED
        request.processed_at = datetime.utcnow()

        await self.db.commit()

        logger.info(
            f"Export bundle stored for request {request.id}, expires in {expiry_days} days"
        )

        return export_url
