"""Trust scoring models: endorsements, scores, and calculation logs.

Domain: Trust verification system that computes trust scores from:
- Performance stability (historical win rate, Sharpe ratio, tenure)
- Social endorsements (peer-to-peer verification)
- Anti-gaming mechanisms (weight caps)
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship

from backend.app.core.db import Base


class Endorsement(Base):
    """User endorsement of another user's trading performance.

    Represents a peer-to-peer verification that one user trusts another's
    trading ability. Weights are capped to prevent manipulation.

    Attributes:
        id: Unique endorsement identifier
        endorser_id: User giving the endorsement
        endorsee_id: User receiving the endorsement
        weight: Trust weight (0.0-1.0, capped at 0.5 anti-gaming)
        reason: Optional reason for endorsement
        created_at: When endorsement was created
        revoked_at: When endorsement was revoked (if any)

    Example:
        >>> endorsement = Endorsement(
        ...     endorser_id="user1",
        ...     endorsee_id="user2",
        ...     weight=0.4,
        ...     reason="Consistent profitable trading"
        ... )
    """

    __tablename__ = "endorsements"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    endorser_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    endorsee_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    weight = Column(Float, nullable=False, default=0.3)  # 0.0-1.0, capped at 0.5
    reason = Column(Text, nullable=True)  # Optional: why endorsing
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    revoked_at = Column(DateTime, nullable=True)  # When endorsement revoked

    # Relationships
    endorser = relationship(
        "User", foreign_keys=[endorser_id], back_populates="endorsements_given"
    )
    endorsee = relationship(
        "User", foreign_keys=[endorsee_id], back_populates="endorsements_received"
    )

    # Indexes
    __table_args__ = (
        Index("ix_endorsements_endorsee_created", "endorsee_id", "created_at"),
        Index("ix_endorsements_endorser_created", "endorser_id", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<Endorsement {self.endorser_id}→{self.endorsee_id} weight={self.weight}>"
        )


class UserTrustScore(Base):
    """Computed trust score for a user.

    Stores the most recent trust score calculation including component breakdown.
    Scores are deterministic based on graph state, enabling caching.

    Attributes:
        id: Unique score identifier
        user_id: User this score belongs to
        score: Overall trust score (0.0-100.0)
        performance_component: Score from performance metrics
        tenure_component: Score from account age/history
        endorsement_component: Score from peer endorsements
        tier: Trust tier (bronze, silver, gold)
        percentile: User's percentile among all users (0-100)
        calculated_at: When score was calculated
        valid_until: When score should be recalculated

    Example:
        >>> trust_score = UserTrustScore(
        ...     user_id="user1",
        ...     score=75.5,
        ...     performance_component=80.0,
        ...     tenure_component=70.0,
        ...     endorsement_component=65.0,
        ...     tier="silver",
        ...     percentile=65
        ... )
    """

    __tablename__ = "user_trust_scores"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id"), nullable=False, unique=True, index=True
    )
    score = Column(Float, nullable=False, default=0.0)  # 0.0-100.0
    performance_component = Column(Float, nullable=False, default=0.0)  # From analytics
    tenure_component = Column(Float, nullable=False, default=0.0)  # From account age
    endorsement_component = Column(
        Float, nullable=False, default=0.0
    )  # From peer endorsements
    tier = Column(String(20), nullable=False, default="bronze")  # bronze|silver|gold
    percentile = Column(Integer, nullable=False, default=0)  # 0-100
    calculated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    valid_until = Column(
        DateTime, nullable=False, default=lambda: datetime.utcnow()
    )  # TTL for refresh

    # Relationship
    user = relationship("User", back_populates="trust_score")

    # Indexes
    __table_args__ = (
        Index("ix_trust_scores_tier", "tier"),
        Index("ix_trust_scores_score", "score"),
    )

    def __repr__(self) -> str:
        return (
            f"<UserTrustScore user={self.user_id} score={self.score} tier={self.tier}>"
        )


class TrustCalculationLog(Base):
    """Audit log of trust score calculations.

    Records every trust score calculation for debugging, audit trail,
    and analytics on score changes over time.

    Attributes:
        id: Unique log entry identifier
        user_id: User whose score was calculated
        previous_score: Prior score before this calculation
        new_score: Calculated score
        input_graph_nodes: Number of users in graph
        input_graph_edges: Number of endorsements considered
        algorithm_version: Version of calculation algorithm
        calculated_at: When calculation occurred
        notes: Optional calculation notes/anomalies

    Example:
        >>> log = TrustCalculationLog(
        ...     user_id="user1",
        ...     previous_score=70.0,
        ...     new_score=75.5,
        ...     input_graph_nodes=1000,
        ...     input_graph_edges=5432,
        ...     algorithm_version="1.0"
        ... )
    """

    __tablename__ = "trust_calculation_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    previous_score = Column(Float, nullable=True)  # Prior score
    new_score = Column(Float, nullable=False)  # Newly calculated score
    input_graph_nodes = Column(Integer, nullable=False, default=0)  # Nodes in graph
    input_graph_edges = Column(Integer, nullable=False, default=0)  # Edges in graph
    algorithm_version = Column(String(20), nullable=False, default="1.0")
    calculated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, index=True
    )
    notes = Column(Text, nullable=True)

    # Relationship
    user = relationship("User")

    # Indexes
    __table_args__ = (Index("ix_calc_logs_user_date", "user_id", "calculated_at"),)

    def __repr__(self) -> str:
        return (
            f"<TrustCalcLog user={self.user_id} {self.previous_score}→{self.new_score}>"
        )
