"""Education Content Pipeline & Quiz Engine.

Serves micro-courses with quizzes, progress tracking, and rewards (credits/discounts).
Supports educational content delivery, quiz attempts, scoring, and reward issuance.

PR-064 Implementation.
"""

from backend.app.education import models, rewards, routes, service

__all__ = ["models", "routes", "service", "rewards"]
