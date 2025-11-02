"""Revenue module for business analytics and KPIs.

Provides revenue tracking, MRR/ARR calculations, churn analysis,
and cohort retention analysis for owner dashboards.
"""

from backend.app.revenue.routes import router as revenue_router

__all__ = ["revenue_router"]
