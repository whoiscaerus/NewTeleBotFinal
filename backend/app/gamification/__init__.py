"""Gamification module for PR-088.

Provides badges, trader levels, XP tracking, and privacy-safe leaderboards
to boost user retention and engagement.
"""

from backend.app.gamification.models import Badge, EarnedBadge, LeaderboardOptIn, Level

__all__ = ["Badge", "EarnedBadge", "Level", "LeaderboardOptIn"]
