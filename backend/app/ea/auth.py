"""
PR-042: Encrypted Signal Transport - Auth & Device Key Generation

Manages device registration, encryption key issuance, and key rotation.
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import Boolean, Column, DateTime, LargeBinary, String
from sqlalchemy.orm import Session

from backend.app.core.db import Base
from backend.app.ea.crypto import DeviceKeyManager


class DeviceEncryptionKey(Base):
    """Encryption key for device - persisted in DB."""

    __tablename__ = "device_encryption_keys"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    device_id = Column(String(36), nullable=False, index=True)
    key_material = Column(LargeBinary, nullable=False)  # Encrypted with master key
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    rotation_token = Column(String(128), unique=True)  # For graceful rotation


class DeviceAuthService:
    """
    Manages device authentication and encryption key lifecycle.
    Issues keys on registration, handles rotation, revocation.
    """

    def __init__(self, key_manager: DeviceKeyManager):
        """
        Initialize auth service.

        Args:
            key_manager: DeviceKeyManager instance
        """
        self.key_manager = key_manager

    def register_device(self, db: Session, user_id: str) -> dict:
        """
        Register new device and issue encryption key.

        Args:
            db: Database session
            user_id: User identifier

        Returns:
            Device credentials dict with device_id, secret, encryption material
        """
        device_id = str(uuid.uuid4())
        rotation_token = str(uuid.uuid4())

        # Create encryption key
        key_obj = self.key_manager.create_device_key(device_id)

        # Persist to DB
        db_key = DeviceEncryptionKey(
            id=str(uuid.uuid4()),
            device_id=device_id,
            key_material=key_obj.encryption_key,
            created_at=key_obj.created_at,
            expires_at=key_obj.expires_at,
            is_active=True,
            rotation_token=rotation_token,
        )
        db.add(db_key)
        db.commit()

        return {
            "device_id": device_id,
            "secret_key": rotation_token,  # Share only once
            "encryption_key_b64": key_obj.encryption_key.hex(),
            "created_at": key_obj.created_at.isoformat(),
            "expires_at": key_obj.expires_at.isoformat(),
        }

    def rotate_device_key(self, db: Session, device_id: str) -> dict:
        """
        Rotate device encryption key (grace period before old key expires).

        Args:
            db: Database session
            device_id: Device identifier

        Returns:
            New key details + grace period info
        """
        # Mark old key as inactive
        old_keys = (
            db.query(DeviceEncryptionKey)
            .filter_by(device_id=device_id, is_active=True)
            .all()
        )
        for old_key in old_keys:
            old_key.is_active = False

        db.commit()

        # Create new key
        new_key_obj = self.key_manager.create_device_key(device_id)
        rotation_token = str(uuid.uuid4())

        db_key = DeviceEncryptionKey(
            id=str(uuid.uuid4()),
            device_id=device_id,
            key_material=new_key_obj.encryption_key,
            created_at=new_key_obj.created_at,
            expires_at=new_key_obj.expires_at,
            is_active=True,
            rotation_token=rotation_token,
        )
        db.add(db_key)
        db.commit()

        return {
            "device_id": device_id,
            "new_secret_key": rotation_token,
            "old_key_grace_period_days": 7,
            "expires_at": new_key_obj.expires_at.isoformat(),
        }

    def revoke_device_key(self, db: Session, device_id: str):
        """
        Revoke device key immediately (e.g., on device unlink).

        Args:
            db: Database session
            device_id: Device identifier
        """
        keys = db.query(DeviceEncryptionKey).filter_by(device_id=device_id).all()
        for key in keys:
            key.is_active = False

        db.commit()
        self.key_manager.revoke_device_key(device_id)

    def get_device_key(self, db: Session, device_id: str) -> DeviceEncryptionKey | None:
        """
        Retrieve active key for device.

        Args:
            db: Database session
            device_id: Device identifier

        Returns:
            Active key or None
        """
        key = (
            db.query(DeviceEncryptionKey)
            .filter_by(device_id=device_id, is_active=True)
            .order_by(DeviceEncryptionKey.created_at.desc())
            .first()
        )

        if key and key.expires_at > datetime.utcnow():
            return key

        return None

    def check_key_expiry(self, db: Session, days_threshold: int = 14) -> dict:
        """
        Check for keys expiring soon and flag for rotation.

        Args:
            db: Database session
            days_threshold: Warning threshold in days

        Returns:
            List of devices needing rotation
        """
        expiry_date = datetime.utcnow() + timedelta(days=days_threshold)
        expiring_keys = (
            db.query(DeviceEncryptionKey)
            .filter(
                DeviceEncryptionKey.expires_at <= expiry_date,
                DeviceEncryptionKey.is_active,
            )
            .all()
        )

        return {
            "expiring_soon_count": len(expiring_keys),
            "devices": [key.device_id for key in expiring_keys],
        }
