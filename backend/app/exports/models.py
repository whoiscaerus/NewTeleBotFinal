"""
PR-057: Export Models

Models for export tokens and share links.
"""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from backend.app.core.db import Base


class ExportToken(Base):
    """Export token for public share links.

    Attributes:
        id: Unique token ID (UUID)
        user_id: Owner of the export
        token: URL-safe token (unique)
        format: Export format (csv or json)
        expires_at: Token expiration timestamp
        accessed_count: Number of times accessed
        max_accesses: Maximum allowed accesses (single-use if 1)
        revoked: Whether token has been revoked
        created_at: Creation timestamp
        last_accessed_at: Last access timestamp
    """

    __tablename__ = "export_tokens"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), nullable=False, index=True)
    token = Column(String(64), unique=True, nullable=False, index=True)
    format = Column(String(10), nullable=False)  # csv or json
    expires_at = Column(DateTime, nullable=False)
    accessed_count = Column(Integer, default=0, nullable=False)
    max_accesses = Column(Integer, default=1, nullable=False)  # single-use by default
    revoked = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_accessed_at = Column(DateTime, nullable=True)

    def is_valid(self) -> bool:
        """Check if token is still valid."""
        if self.revoked:
            return False
        if datetime.utcnow() > self.expires_at:
            return False
        if self.accessed_count >= self.max_accesses:
            return False
        return True

    def __repr__(self):
        return f"<ExportToken {self.token[:8]}... expires={self.expires_at}>"
