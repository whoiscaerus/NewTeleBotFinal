# User Model Relationship Architecture

**Document**: Clarification of three User relationships (AccountLink, Endorsement, UserTrustScore)
**Status**: CURRENT ARCHITECTURE ANALYSIS
**Date**: October 2024

---

## Overview

The `User` model in `/backend/app/auth/models.py` defines three relationships that connect to other business domains:

| Relationship | Status | PR | Purpose | Implementation |
|---|---|---|---|---|
| **account_links** | ✅ ENABLED | PR-043 | Link Telegram users to MT5 trading accounts | Full implementation exists |
| **endorsements_given** | ❌ COMMENTED | PR-024 | Track endorsements given to other users (affiliate trust) | Model not yet created |
| **endorsements_received** | ❌ COMMENTED | PR-024 | Track endorsements received from other users (affiliate trust) | Model not yet created |
| **trust_score** | ❌ COMMENTED | PR-024 | Aggregate trust metrics for affiliate verification | Model not yet created |

---

## Detailed Breakdown

### 1. AccountLink (✅ IMPLEMENTED - PR-043)

**What it is:**
- Links a Telegram user to their MetaTrader 5 (MT5) trading account
- Supports multiple accounts per user (each Telegram user can have many MT5 accounts)
- One account can be marked as "primary" for default polling

**Business Purpose:**
- **Account Verification**: Users verify they own their MT5 account (prevents unauthorized access)
- **Multi-Account Management**: Users with multiple brokers/accounts can manage all from one Telegram bot
- **Account-Specific Signals**: System knows which MT5 account to send signals to
- **Live Position Tracking**: Real-time account equity and position monitoring (PR-043 feature)

**Implementation Status:**
```python
# Location: /backend/app/auth/models.py (lines 58-65)
account_links: Mapped[list] = relationship(
    "AccountLink",
    back_populates="user",
    cascade="all, delete-orphan",
    lazy="select",
)
```

**Model Definition:**
```python
# Location: /backend/app/accounts/models.py (lines 26-61)
class AccountLink(Base):
    __tablename__ = "account_links"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    mt5_account_id = Column(String(255), nullable=False)      # Account number
    mt5_login = Column(String(255), nullable=False)           # Login for MT5
    broker_name = Column(String(100), default="MetaTrader5")  # Broker name
    is_primary = Column(Boolean, default=False)               # Primary account flag
    verified_at = Column(DateTime, nullable=True)             # Verification timestamp
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime)
    
    # Relationships
    user = relationship("User", back_populates="account_links")
    account_info = relationship("AccountInfo", cascade="all, delete-orphan")
```

**Example Use Case:**
```
User "Alice" (Telegram: @alice_trader):
  ├─ AccountLink 1: MT5 Account 12345678 (Broker A, primary, verified)
  ├─ AccountLink 2: MT5 Account 87654321 (Broker B, secondary, not verified)
  └─ AccountLink 3: MT5 Account 11111111 (Broker C, secondary, verified)

When Alice requests signals:
→ System polls all 3 accounts
→ If she has EA connected to Broker A account, executes trades there
→ Admin can verify account ownership via verified_at timestamp
```

**Why It's Active Now:**
- PR-043 is complete and ready for production
- No dependencies on future features
- Critical for trader lifecycle (user onboarding requires account linking)

---

### 2. Endorsement (❌ NOT IMPLEMENTED - PR-024 Future)

**What it is:**
- Record when one user endorses another user
- Bidirectional: User A can endorse User B, and vice versa
- Tracks endorsement metadata (timestamp, reason, rating)

**Business Purpose (from PR-024 - Affiliate & Referral System):**
- **Affiliate Trust Scoring**: Affiliates need reputation to be credible
- **Referral Quality**: If an affiliate endorses someone, implies they're trustworthy
- **Fraud Detection**: Multiple endorsements from same user might indicate fake accounts
- **Social Proof**: Influencers show endorsements on affiliate page ("Endorsed by 50+ traders")

**Why It Exists But Is Commented Out:**
1. **Model Not Yet Created**: No `Endorsement` class exists yet
2. **PR-024 Not Started**: Affiliate system is not yet implemented
3. **Prevents Mapper Errors**: SQLAlchemy would fail if User references non-existent Endorsement class
4. **Future-Proofing**: Architecture is ready for PR-024; just needs implementation

**Planned PR-024 Implementation:**
```python
# FUTURE: This will be created when PR-024 is implemented
class Endorsement(Base):
    __tablename__ = "endorsements"
    
    id = Column(String(36), primary_key=True)
    endorser_id = Column(String(36), ForeignKey("users.id"), nullable=False)  # User giving endorsement
    endorsee_id = Column(String(36), ForeignKey("users.id"), nullable=False)   # User receiving endorsement
    rating = Column(Integer, nullable=False)  # 1-5 stars
    reason = Column(String(500), nullable=True)  # Why endorsing
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Bidirectional relationships to User
    endorser = relationship("User", foreign_keys=[endorser_id], back_populates="endorsements_given")
    endorsee = relationship("User", foreign_keys=[endorsee_id], back_populates="endorsements_received")
```

**Example Use Case (When PR-024 Launches):**
```
Influencer "Bob" (@bob_trader) becomes affiliate:
  Bob's endorsements_given:
    ├─ User "Charlie" (⭐⭐⭐⭐⭐ "Great trader, consistent profits")
    ├─ User "Diana" (⭐⭐⭐ "Decent strategy, new to affiliate space")
    └─ User "Eve" (⭐ "Lost my referral money, wouldn't recommend")

When Charlie signs up via Bob's link:
→ System checks Bob's endorsement of Charlie (high rating)
→ Bob gets commission: 30% month 1, 15% recurring
→ If dispute: "Look, I endorsed Charlie highly, and she lost money on her manual trades not mine"
```

---

### 3. UserTrustScore (❌ NOT IMPLEMENTED - PR-024 Future)

**What it is:**
- Aggregate trust metrics for a user
- One-to-one relationship: Each User has exactly one UserTrustScore
- Combines multiple trust signals into a single score

**Business Purpose (from PR-024 - Affiliate & Referral System):**
- **Affiliate Eligibility**: Only high-trust users can become affiliates (prevents fraud)
- **Commission Tier Eligibility**: Higher trust = better commission rates
- **Performance Bonus Qualification**: Trust score determines if affiliate gets 5% performance bonus
- **Self-Referral Detection Blocking**: If User A creates User B with suspicious pattern, both scores drop

**Components of Trust Score (Planned):**
```python
# FUTURE: When PR-024 implements UserTrustScore
class UserTrustScore(Base):
    __tablename__ = "user_trust_scores"
    
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), unique=True, nullable=False)
    
    # Trust signals (computed daily)
    account_age_days = Column(Integer, default=0)            # How long account exists
    endorsement_count = Column(Integer, default=0)           # How many endorsements received
    average_endorsement_rating = Column(Float, default=0)    # Average rating (1-5)
    trade_count = Column(Integer, default=0)                 # Number of trades
    win_rate = Column(Float, default=0)                      # Win rate of their trades
    fraud_flags = Column(Integer, default=0)                 # Red flags found (self-referral, etc)
    account_verified = Column(Boolean, default=False)        # MT5 account verified (AccountLink.verified_at)
    
    # Final score (0-100)
    trust_score = Column(Float, default=0)                   # Computed from above signals
    
    # Thresholds
    affiliate_eligible = Column(Boolean, default=False)      # trust_score >= 60
    commission_tier = Column(Integer, default=1)             # 1=30%, 2=15%, 3=5%
    performance_bonus_eligible = Column(Boolean, default=False)  # trust_score >= 80
    
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    
    user = relationship("User", back_populates="trust_score")
```

**Example Use Case (When PR-024 Launches):**
```
New Trader "Frank" (@frank_trader):
  Created 1 day ago
  No endorsements
  5 manual trades (60% win rate)
  Account linked but not verified
  
  UserTrustScore:
    - trust_score = 15/100 (very low, new account)
    - affiliate_eligible = False (requires >= 60)
    - commission_tier = Not applicable
    - performance_bonus_eligible = False
  
  Result: Can't become affiliate yet

---

Experienced Trader "Grace" (@grace_pro):
  Created 180 days ago
  Endorsed by 12 traders (avg ⭐⭐⭐⭐)
  1,200 trades (72% win rate)
  Multiple accounts verified
  No fraud flags
  
  UserTrustScore:
    - trust_score = 88/100 (high trust)
    - affiliate_eligible = True
    - commission_tier = 3 (gets 5% performance bonus if stays 3+ months)
    - performance_bonus_eligible = True
  
  Result: Can become high-tier affiliate with best commission rates
```

---

## Why These Are Commented Out (Not Deleted)

### Problem Without Comments:
```python
# If Endorsement didn't exist:
account_links = relationship("AccountLink")  # ✅ Works
endorsements_given = relationship("Endorsement")  # ❌ FAILS - SQLAlchemy mapper error
trust_score = relationship("UserTrustScore")  # ❌ FAILS - SQLAlchemy mapper error
```

SQLAlchemy tries to initialize ALL relationships when the mapper starts. If it can't find the model, initialization fails, and **no tests can run**.

### Solution: Comment Out Future Relationships
```python
account_links = relationship("AccountLink")  # ✅ ENABLED - model exists

# endorsements_given = relationship("Endorsement")  # ❌ COMMENTED - PR-024 not started
# endorsements_received = relationship("Endorsement")  # ❌ COMMENTED - PR-024 not started
# trust_score = relationship("UserTrustScore")  # ❌ COMMENTED - PR-024 not started
```

**Benefits:**
1. ✅ Current tests work (AccountLink relationship initializes successfully)
2. ✅ Architecture is visible for future developers (they can see the plan)
3. ✅ No migration needed when PR-024 is implemented (just uncomment)
4. ✅ Clear documentation of what's coming next

---

## Current State Check

**auth/models.py (User model) - Current Status:**
```python
# Lines 58-85 in /backend/app/auth/models.py

# Relationships
# NOTE: AccountLink exists (PR-043), Endorsement and UserTrustScore are future models (PR-024+)
# Only uncommenting account_links which has implemented model
# Keeping Endorsement and UserTrustScore commented out until those PRs complete

account_links: Mapped[list] = relationship(
    "AccountLink",
    back_populates="user",
    cascade="all, delete-orphan",
    lazy="select",
)
# endorsements_given: Mapped[list] = relationship(
#     "Endorsement",
#     foreign_keys="[Endorsement.endorser_id]",
#     back_populates="endorser",
#     lazy="select",
#     viewonly=False,
# )
# endorsements_received: Mapped[list] = relationship(
#     "Endorsement",
#     foreign_keys="[Endorsement.endorsee_id]",
#     back_populates="endorsee",
#     lazy="select",
#     viewonly=False,
# )
# trust_score: Mapped[object] = relationship(
#     "UserTrustScore", back_populates="user", uselist=False, lazy="select"
# )
```

**Status**: ✅ CORRECT - AccountLink is enabled, others are commented and safe

---

## PR Timeline for These Features

| PR | Feature | Status | Dependencies |
|---|---|---|---|
| **PR-043** | Live Position Tracking & Account Linking (AccountLink model) | ✅ COMPLETE | PR-004 (auth), PR-016 (trade store) |
| **PR-016** | Trade Store Migration (uses Account Links for queries) | 📝 IN PROGRESS | AccountLink implementation ✅ |
| **PR-024** | Affiliate & Referral System (Endorsement, UserTrustScore models) | ⏳ FUTURE | PR-004 (auth), PR-033 (payments), PR-008 (audit) |

**Immediate Impact:**
- PR-016 tests can run NOW (AccountLink is fully implemented)
- PR-024 will uncomment relationships when started (no code changes needed to User model)

---

## Verification: Are These Models Really Implemented?

**AccountLink: ✅ YES**
```bash
File: /backend/app/accounts/models.py
Lines: 26-61 (class definition)
Status: COMPLETE - 94 lines, includes relationships, indexes, constraints
Related: AccountInfo (also implemented), AccountLinkingService (schema + service)
Exports: /backend/app/accounts/__init__.py includes AccountLink in __all__
```

**Endorsement: ❌ NO**
```bash
grep -r "class Endorsement" backend/app/
# Output: (no results - not implemented anywhere)
```

**UserTrustScore: ❌ NO**
```bash
grep -r "class UserTrustScore" backend/app/
# Output: (no results - not implemented anywhere)
```

---

## Impact on PR-016 (Trade Store)

**Current State:**
- PR-016 has 34 tests created and collected
- Tests are temporarily marked `@pytest.mark.skip`
- Reason: User model relationship initialization was being investigated

**Resolution:**
- AccountLink is fully implemented ✅
- Endorsement/UserTrustScore are properly commented out ✅
- User model mapper initializes successfully ✅
- **Next Step**: Remove `@pytest.mark.skip` and run tests

**Expected Result:**
```bash
# After removing skip marker:
pytest backend/tests/test_pr_016_trade_store.py -v
# Expected: 34 tests collected and PASSING
# Expected coverage: 90%+
```

---

## Architecture Philosophy

This project uses a **future-proofing pattern**:

1. **Define relationships early**: Developers can see the full architecture
2. **Comment out incomplete parts**: Prevents runtime errors during development
3. **Use clear documentation**: Explain what's coming and why
4. **No migration burden later**: When feature launches, just uncomment

**This is Production Best Practice** because:
- ✅ New developers see the full system design upfront
- ✅ No technical debt of "hidden" planned features
- ✅ Easy to implement features when time comes
- ✅ Prevents bugs from incomplete implementations

---

## Summary

| Model | Status | When to Uncomment | Action Now |
|---|---|---|---|
| **AccountLink** | ✅ Implemented | Already active | Keep enabled - PR-016 depends on it |
| **Endorsement** | ❌ Future (PR-024) | When PR-024 starts | Leave commented - safe for now |
| **UserTrustScore** | ❌ Future (PR-024) | When PR-024 starts | Leave commented - safe for now |

**Current Action**: Remove `@pytest.mark.skip` from PR-016 tests → Run full suite → Measure 90%+ coverage

