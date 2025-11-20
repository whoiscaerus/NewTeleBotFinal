"""Social Verification Graph - Database Models.

PR-094: User peer verification edges with anti-sybil metadata.
"""

import logging
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, String
from sqlalchemy.orm import relationship

from backend.app.core.db import Base

logger = logging.getLogger(__name__)


class VerificationEdge(Base):
    """Verification edge representing trust relationship between users.

    Represents "User A verified User B" with metadata for anti-gaming:
    - Weight: Strength of verification (1.0 default, can be adjusted by system)
    - IP address: For anti-sybil detection (same IP repeatedly = suspicious)
    - Device fingerprint: For multi-account detection
    - Created timestamp: For rate limiting (X verifications per time window)

    Attributes:
        id: Unique identifier
        verifier_id: User who is doing the verification
        verified_id: User who is being verified
        weight: Verification strength (0.0-1.0, default 1.0)
        created_at: When verification was created
        ip_address: IP address of verifier (for anti-sybil)
        device_fingerprint: Device identifier (for anti-sybil)
        notes: Optional verification note/reason
    """

    __tablename__ = "verification_edges"

    id = Column(String(36), primary_key=True)
    verifier_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    verified_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    weight = Column(Float, nullable=False, default=1.0)  # 0.0-1.0
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    ip_address = Column(String(45), nullable=True)  # IPv6 max length
    device_fingerprint = Column(String(64), nullable=True)  # Hash of device info
    notes = Column(String(500), nullable=True)

    # Relationships
    verifier = relationship(
        "User",
        foreign_keys=[verifier_id],
        back_populates="given_verifications",
        lazy="selectin",
    )
    verified = relationship(
        "User",
        foreign_keys=[verified_id],
        back_populates="received_verifications",
        lazy="selectin",
    )

    __table_args__ = (
        # Prevent duplicate verifications (same verifier → verified pair)
        Index(
            "ix_verification_unique_pair",
            "verifier_id",
            "verified_id",
            unique=True,
        ),
        # Query verifications by verifier (for rate limiting)
        Index("ix_verification_verifier_created", "verifier_id", "created_at"),
        # Query verifications received by user
        Index("ix_verification_verified_created", "verified_id", "created_at"),
        # Anti-sybil: query by IP address
        Index("ix_verification_ip_created", "ip_address", "created_at"),
        # Anti-sybil: query by device
        Index("ix_verification_device_created", "device_fingerprint", "created_at"),
    )

    def __repr__(self):
        return f"<VerificationEdge {self.verifier_id[:8]}→{self.verified_id[:8]} weight={self.weight}>"
