"""
Comprehensive tests for PR-095: Public Trust Index with PR-094 Social Graph Integration.

Tests trust band calculation with social influence, zero data edge cases,
and trust index API to validate 100% working business logic.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.models import User
from backend.app.public.trust_index import (
    PublicTrustIndexRecord,
    calculate_trust_band,
    calculate_trust_index,
)
from backend.app.trading.store.models import Trade
from backend.app.trust.social.models import VerificationEdge

# ============================================================================
# Trust Band Calculation Tests (Without Social Graph)
# ============================================================================


def test_calculate_trust_band_unverified():
    """Test calculate_trust_band returns 'unverified' for <50% composite score."""
    # 40% accuracy, 0% influence → 0.4 * 0.7 + 0.0 * 0.3 = 0.28 < 0.50
    band = calculate_trust_band(
        accuracy_metric=0.40,
        average_rr=1.5,
        verified_trades_pct=50,
        influence_score=0.0,
    )
    assert band == "unverified"


def test_calculate_trust_band_verified():
    """Test calculate_trust_band returns 'verified' for ≥50% composite score."""
    # 60% accuracy, 10% influence → 0.6 * 0.7 + 0.1 * 0.3 = 0.45 < 0.50 (unverified)
    # 70% accuracy, 10% influence → 0.7 * 0.7 + 0.1 * 0.3 = 0.52 ≥ 0.50 (verified)
    band = calculate_trust_band(
        accuracy_metric=0.72,
        average_rr=1.5,
        verified_trades_pct=60,
        influence_score=0.10,
    )
    assert band == "verified"


def test_calculate_trust_band_expert():
    """Test calculate_trust_band returns 'expert' for ≥60% composite score."""
    # 70% accuracy, 30% influence → 0.7 * 0.7 + 0.3 * 0.3 = 0.58 < 0.60 (verified)
    # 75% accuracy, 30% influence → 0.75 * 0.7 + 0.3 * 0.3 = 0.615 ≥ 0.60 (expert)
    band = calculate_trust_band(
        accuracy_metric=0.75,
        average_rr=2.0,
        verified_trades_pct=80,
        influence_score=0.30,
    )
    assert band == "expert"


def test_calculate_trust_band_elite():
    """Test calculate_trust_band returns 'elite' for ≥75% composite score."""
    # 90% accuracy, 50% influence → 0.9 * 0.7 + 0.5 * 0.3 = 0.78 ≥ 0.75 (elite)
    band = calculate_trust_band(
        accuracy_metric=0.90,
        average_rr=2.5,
        verified_trades_pct=95,
        influence_score=0.50,
    )
    assert band == "elite"


# ============================================================================
# Trust Band Calculation Tests (With Social Graph Integration - PR-094)
# ============================================================================


def test_trust_band_social_graph_boosts_verified_to_expert():
    """Test high social influence boosts 'verified' tier to 'expert'."""
    # 55% accuracy alone → verified tier
    # But with 50% influence → 0.55 * 0.7 + 0.5 * 0.3 = 0.535 < 0.60 (verified)
    # Need 60% accuracy + 50% influence → 0.6 * 0.7 + 0.5 * 0.3 = 0.57 < 0.60 (verified)
    # Need 65% accuracy + 50% influence → 0.65 * 0.7 + 0.5 * 0.3 = 0.605 ≥ 0.60 (expert)
    band = calculate_trust_band(
        accuracy_metric=0.65,
        average_rr=1.8,
        verified_trades_pct=70,
        influence_score=0.50,
    )
    assert band == "expert"


def test_trust_band_social_graph_boosts_expert_to_elite():
    """Test high social influence boosts 'expert' tier to 'elite'."""
    # 65% accuracy alone → expert tier
    # But with 80% influence → 0.65 * 0.7 + 0.8 * 0.3 = 0.695 < 0.75 (expert)
    # Need 70% accuracy + 80% influence → 0.7 * 0.7 + 0.8 * 0.3 = 0.73 < 0.75 (expert)
    # Need 75% accuracy + 80% influence → 0.75 * 0.7 + 0.8 * 0.3 = 0.765 ≥ 0.75 (elite)
    band = calculate_trust_band(
        accuracy_metric=0.75,
        average_rr=2.2,
        verified_trades_pct=90,
        influence_score=0.80,
    )
    assert band == "elite"


def test_trust_band_low_accuracy_high_influence_still_unverified():
    """Test high influence cannot overcome very low accuracy."""
    # 30% accuracy, 90% influence → 0.3 * 0.7 + 0.9 * 0.3 = 0.48 < 0.50 (unverified)
    band = calculate_trust_band(
        accuracy_metric=0.30,
        average_rr=1.0,
        verified_trades_pct=20,
        influence_score=0.90,
    )
    assert band == "unverified"


def test_trust_band_zero_influence_accuracy_only():
    """Test trust band calculation with zero social influence (accuracy-only)."""
    # 60% accuracy, 0% influence → 0.6 * 0.7 + 0.0 * 0.3 = 0.42 < 0.50 (unverified)
    # Need 72% accuracy, 0% influence → 0.72 * 0.7 = 0.504 ≥ 0.50 (verified)
    band = calculate_trust_band(
        accuracy_metric=0.72,
        average_rr=1.5,
        verified_trades_pct=60,
        influence_score=0.0,
    )
    assert band == "verified"


# ============================================================================
# Trust Index Calculation Tests (Zero Data Edge Cases)
# ============================================================================


@pytest.mark.asyncio
async def test_calculate_trust_index_no_trades(db_session: AsyncSession):
    """Test calculate_trust_index with user who has no trades."""
    user = User(
        id="user1", email="user1@test.com", password_hash="hashed_pwd",
        telegram_user_id=12345,
        role="user",
        created_at=datetime.utcnow() - timedelta(days=30),
    )
    db_session.add(user)
    await db_session.commit()

    # Calculate trust index (no trades)
    index = await calculate_trust_index("user1", db_session)

    assert index is not None
    assert index.user_id == "user1"
    assert index.accuracy_metric == 0.0  # No trades → 0% accuracy
    assert index.average_rr == 1.0  # Default neutral value
    assert index.verified_trades_pct == 0  # No trades → 0% verified
    assert index.trust_band == "unverified"  # 0% accuracy → unverified


@pytest.mark.asyncio
async def test_calculate_trust_index_with_trades(db_session: AsyncSession):
    """Test calculate_trust_index with user who has closed trades."""
    user = User(
        id="user1", email="user1@test.com", password_hash="hashed_pwd",
        telegram_user_id=12345,
        role="user",
        created_at=datetime.utcnow() - timedelta(days=30),
    )
    db_session.add(user)
    await db_session.commit()

    # Create 10 closed trades: 7 winning, 3 losing
    trades = []
    for i in range(10):
        profit = 100.0 if i < 7 else -50.0  # First 7 win, last 3 lose
        entry_price = 1900.0
        exit_price = 1950.0 if profit > 0 else 1850.0
        trade = Trade(
            trade_id=f"trade{i}",  # was id
            user_id="user1",
            symbol="XAUUSD",  # was instrument
            strategy="fib_rsi",  # required
            timeframe="H1",  # required
            trade_type="BUY",
            direction=0,  # was side
            entry_price=entry_price,
            entry_time=datetime.utcnow() - timedelta(hours=i),
            stop_loss=entry_price * 0.98,  # required: 2% below entry
            take_profit=entry_price * 1.04,  # required: 4% above entry
            volume=0.1,  # was quantity
            exit_price=exit_price,
            exit_time=datetime.utcnow() - timedelta(hours=i, minutes=30),
            profit=profit,
            risk_reward_ratio=2.0 if profit > 0 else 0.5,
            status="CLOSED",
            signal_id=f"signal{i}" if i < 5 else None,  # First 5 are verified
        )
        trades.append(trade)
    db_session.add_all(trades)
    await db_session.commit()

    # Calculate trust index
    index = await calculate_trust_index("user1", db_session)

    assert index is not None
    assert index.user_id == "user1"
    assert index.accuracy_metric == 0.7  # 7/10 = 70%
    # Average RR: (2.0 * 7 + 0.5 * 3) / 10 = 15.5 / 10 = 1.55
    assert index.average_rr == pytest.approx(1.55, rel=0.01)
    assert index.verified_trades_pct == 50  # 5/10 = 50%
    # 70% accuracy, 0% influence → 0.7 * 0.7 = 0.49 < 0.50 (unverified)
    # BUT with no social graph verifications → unverified
    # Actually: 0.7 * 0.7 + 0.0 * 0.3 = 0.49 < 0.50 → unverified
    # Need 72% accuracy → 0.72 * 0.7 = 0.504 ≥ 0.50 → verified
    # So 70% accuracy should be unverified with 0 influence
    assert index.trust_band == "unverified"


@pytest.mark.asyncio
async def test_calculate_trust_index_integrates_social_graph(db_session: AsyncSession):
    """Test calculate_trust_index integrates PR-094 social graph influence."""
    # Create user with trades
    user1 = User(
        id="user1", email="user1@test.com", password_hash="hashed_pwd",
        telegram_user_id=12345,
        role="user",
        created_at=datetime.utcnow() - timedelta(days=30),
    )
    db_session.add(user1)
    await db_session.commit()

    # Create 10 closed trades: 7 winning (70% accuracy)
    trades = []
    for i in range(10):
        profit = 100.0 if i < 7 else -50.0
        entry_price = 1900.0
        exit_price = 1950.0 if profit > 0 else 1850.0
        trade = Trade(
            trade_id=f"trade{i}",  # was id
            user_id="user1",
            symbol="XAUUSD",  # was instrument
            strategy="fib_rsi",  # required
            timeframe="H1",  # required
            trade_type="BUY",
            direction=0,  # was side
            entry_price=entry_price,
            entry_time=datetime.utcnow() - timedelta(hours=i),
            stop_loss=entry_price * 0.98,  # required
            take_profit=entry_price * 1.04,  # required
            volume=0.1,  # was quantity
            exit_price=exit_price,
            exit_time=datetime.utcnow() - timedelta(hours=i, minutes=30),
            profit=profit,
            risk_reward_ratio=2.0 if profit > 0 else 0.5,
            status="CLOSED",
            signal_id=f"signal{i}" if i < 5 else None,
        )
        trades.append(trade)
    db_session.add_all(trades)
    await db_session.commit()

    # Create 3 other users who verify user1 (user1 gets 3 verifications)
    verifiers = []
    for i in range(2, 5):
        verifier = User(
            id=f"user{i}",
            email=f"user{i}@test.com",
            password_hash="hashed_pwd",
            telegram_user_id=10000 + i,
            role="user",
            created_at=datetime.utcnow() - timedelta(days=30),
        )
        verifiers.append(verifier)
    db_session.add_all(verifiers)
    await db_session.commit()

    # Create verification edges
    for i in range(2, 5):
        edge = VerificationEdge(
            id=f"edge{i}",
            verifier_id=f"user{i}",
            verified_id="user1",
            weight=1.0,
            created_at=datetime.utcnow(),
            ip_address=f"192.168.1.{i}",
            device_fingerprint=f"device{i}",
        )
        db_session.add(edge)
    await db_session.commit()

    # Calculate trust index (should integrate social graph)
    index = await calculate_trust_index("user1", db_session)

    assert index is not None
    assert index.accuracy_metric == 0.7  # 70% accuracy
    # Influence score: 3 verifications → 3.0 / (1 + 3) = 0.75
    # Composite: 0.7 * 0.7 + 0.75 * 0.3 = 0.49 + 0.225 = 0.715 ≥ 0.60 (expert)
    assert (
        index.trust_band == "expert"
    )  # Social graph boosts from unverified to expert!


@pytest.mark.asyncio
async def test_calculate_trust_index_high_influence_boosts_to_elite(
    db_session: AsyncSession,
):
    """Test high social influence boosts trust band to elite tier."""
    # Create user with good trades (75% accuracy)
    user1 = User(
        id="user1", email="user1@test.com", password_hash="hashed_pwd",
        telegram_user_id=12345,
        role="user",
        created_at=datetime.utcnow() - timedelta(days=30),
    )
    db_session.add(user1)
    await db_session.commit()

    # Create 20 closed trades: 15 winning (75% accuracy)
    trades = []
    for i in range(20):
        profit = 100.0 if i < 15 else -50.0
        entry_price = 1900.0
        exit_price = 1950.0 if profit > 0 else 1850.0
        trade = Trade(
            trade_id=f"trade{i}",
            user_id="user1",
            symbol="XAUUSD",
            strategy="fib_rsi",
            timeframe="H1",
            trade_type="BUY",
            direction=0,
            entry_price=entry_price,
            exit_price=exit_price,
            volume=0.1,
            profit=profit,
            risk_reward_ratio=2.0 if profit > 0 else 0.5,
            status="CLOSED",
            stop_loss=entry_price * 0.98,
            take_profit=entry_price * 1.04,
            signal_id=f"signal{i}" if i < 10 else None,
            entry_time=datetime.utcnow() - timedelta(hours=i),
            exit_time=datetime.utcnow() - timedelta(hours=i, minutes=30),
        )
        trades.append(trade)
    db_session.add_all(trades)
    await db_session.commit()

    # Create 9 other users who verify user1 (high influence)
    verifiers = []
    for i in range(2, 11):
        verifier = User(
            id=f"user{i}",
            email=f"user{i}@test.com",
            password_hash="hashed_pwd",
            telegram_user_id=10000 + i,
            role="user",
            created_at=datetime.utcnow() - timedelta(days=30),
        )
        verifiers.append(verifier)
    db_session.add_all(verifiers)
    await db_session.commit()

    # Create verification edges
    for i in range(2, 11):
        edge = VerificationEdge(
            id=f"edge{i}",
            verifier_id=f"user{i}",
            verified_id="user1",
            weight=1.0,
            created_at=datetime.utcnow(),
            ip_address=f"192.168.1.{i}",
            device_fingerprint=f"device{i}",
        )
        db_session.add(edge)
    await db_session.commit()

    # Calculate trust index
    index = await calculate_trust_index("user1", db_session)

    assert index is not None
    assert index.accuracy_metric == 0.75  # 75% accuracy
    # Influence score: 9 verifications → 9.0 / (1 + 9) = 0.9
    # Composite: 0.75 * 0.7 + 0.9 * 0.3 = 0.525 + 0.27 = 0.795 ≥ 0.75 (elite)
    assert index.trust_band == "elite"


@pytest.mark.asyncio
async def test_calculate_trust_index_caching(db_session: AsyncSession):
    """Test calculate_trust_index returns cached record within TTL."""
    user = User(
        id="user1", email="user1@test.com", password_hash="hashed_pwd",
        telegram_user_id=12345,
        role="user",
        created_at=datetime.utcnow() - timedelta(days=30),
    )
    db_session.add(user)
    await db_session.commit()

    # Create existing cached record (still valid)
    existing = PublicTrustIndexRecord(
        id="record1",
        user_id="user1",
        accuracy_metric=0.85,
        average_rr=2.5,
        verified_trades_pct=90,
        trust_band="elite",
        calculated_at=datetime.utcnow() - timedelta(hours=12),  # 12h ago
        valid_until=datetime.utcnow() + timedelta(hours=12),  # Still valid for 12h
        notes="Cached",
    )
    db_session.add(existing)
    await db_session.commit()

    # Calculate trust index (should return cached)
    index = await calculate_trust_index("user1", db_session)

    assert index is not None
    assert index.accuracy_metric == 0.85  # From cache
    assert index.trust_band == "elite"  # From cache


@pytest.mark.asyncio
async def test_calculate_trust_index_user_not_found(db_session: AsyncSession):
    """Test calculate_trust_index raises ValueError for non-existent user."""
    with pytest.raises(ValueError, match="User nonexistent not found"):
        await calculate_trust_index("nonexistent", db_session)


# ============================================================================
# Edge Case Tests
# ============================================================================


@pytest.mark.asyncio
async def test_trust_index_all_losing_trades(db_session: AsyncSession):
    """Test trust index with user who has all losing trades."""
    user = User(
        id="user1", email="user1@test.com", password_hash="hashed_pwd",
        telegram_user_id=12345,
        role="user",
        created_at=datetime.utcnow() - timedelta(days=30),
    )
    db_session.add(user)
    await db_session.commit()

    # Create 5 closed trades: all losing
    trades = []
    for i in range(5):
        entry_price = 1900.0
        exit_price = 1850.0  # All losing
        trade = Trade(
            trade_id=f"trade{i}",
            user_id="user1",
            symbol="XAUUSD",
            strategy="fib_rsi",
            timeframe="H1",
            trade_type="BUY",
            direction=0,
            entry_price=entry_price,
            exit_price=exit_price,
            volume=0.1,
            profit=-50.0,
            risk_reward_ratio=0.5,
            status="CLOSED",
            stop_loss=entry_price * 0.98,
            take_profit=entry_price * 1.04,
            signal_id=None,
            entry_time=datetime.utcnow() - timedelta(hours=i),
            exit_time=datetime.utcnow() - timedelta(hours=i, minutes=30),
        )
        trades.append(trade)
    db_session.add_all(trades)
    await db_session.commit()

    # Calculate trust index
    index = await calculate_trust_index("user1", db_session)

    assert index is not None
    assert index.accuracy_metric == 0.0  # 0/5 = 0%
    assert index.trust_band == "unverified"


@pytest.mark.asyncio
async def test_trust_index_all_verified_trades(db_session: AsyncSession):
    """Test trust index with user who has 100% verified trades."""
    user = User(
        id="user1", email="user1@test.com", password_hash="hashed_pwd",
        telegram_user_id=12345,
        role="user",
        created_at=datetime.utcnow() - timedelta(days=30),
    )
    db_session.add(user)
    await db_session.commit()

    # Create 10 closed trades: all with signal_id (100% verified)
    trades = []
    for i in range(10):
        profit = 100.0 if i < 8 else -50.0  # 80% accuracy
        entry_price = 1900.0
        exit_price = 1950.0 if profit > 0 else 1850.0
        trade = Trade(
            trade_id=f"trade{i}",
            user_id="user1",
            symbol="XAUUSD",
            strategy="fib_rsi",
            timeframe="H1",
            trade_type="BUY",
            direction=0,
            entry_price=entry_price,
            exit_price=exit_price,
            volume=0.1,
            profit=profit,
            risk_reward_ratio=2.0 if profit > 0 else 0.5,
            status="CLOSED",
            stop_loss=entry_price * 0.98,
            take_profit=entry_price * 1.04,
            signal_id=f"signal{i}",  # ALL verified
            entry_time=datetime.utcnow() - timedelta(hours=i),
            exit_time=datetime.utcnow() - timedelta(hours=i, minutes=30),
        )
        trades.append(trade)
    db_session.add_all(trades)
    await db_session.commit()

    # Calculate trust index
    index = await calculate_trust_index("user1", db_session)

    assert index is not None
    assert index.verified_trades_pct == 100  # 10/10 = 100%
    assert index.accuracy_metric == 0.8  # 80% accuracy
    # 80% accuracy, 0% influence → 0.8 * 0.7 = 0.56 ≥ 0.50 (verified)
    assert index.trust_band == "verified"



