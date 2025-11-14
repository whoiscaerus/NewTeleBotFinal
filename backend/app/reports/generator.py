"""
Report generation service (PR-101).

Combines analytics data with AI-generated narratives to create
HTML and PDF reports for clients and owners.
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from jinja2 import Environment, FileSystemLoader
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.analytics.equity import EquityEngine
from backend.app.analytics.metrics import PerformanceMetrics
from backend.app.health.models import Incident, IncidentSeverity
from backend.app.reports.models import Report, ReportPeriod, ReportStatus, ReportType
from backend.app.trading.store.models import Trade
from backend.app.auth.models import User

logger = logging.getLogger(__name__)

# Template directory
TEMPLATES_DIR = Path(__file__).parent / "templates"


class ReportGenerator:
    """
    Service for generating AI-enhanced reports (PR-101).

    Combines analytics, revenue, and system health data into
    narrative HTML/PDF reports for clients and owners.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.equity_engine = EquityEngine(db)
        self.metrics_engine = PerformanceMetrics(db)

        # Initialize Jinja2 template environment
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True
        )

    async def build_report(
        self,
        period: ReportPeriod,
        report_type: ReportType,
        user_id: Optional[str] = None,
    ) -> Report:
        """
        Build a complete report with data collection, HTML generation, and AI summary.

        Args:
            period: Report period (daily, weekly, monthly)
            report_type: CLIENT or OWNER
            user_id: User ID for client reports, None for owner reports

        Returns:
            Report: Report entity with generated content

        Raises:
            ValueError: If client report without user_id
            RuntimeError: If data collection or generation fails

        Example:
            >>> generator = ReportGenerator(db)
            >>> report = await generator.build_report(
            ...     ReportPeriod.WEEKLY,
            ...     ReportType.CLIENT,
            ...     user_id="user_123"
            ... )
            >>> print(report.html_url)
        """
        if report_type == ReportType.CLIENT and not user_id:
            raise ValueError("Client reports require user_id")

        # Calculate date range
        period_start, period_end = self._calculate_period_range(period)

        # Create report entity
        report = Report(
            type=report_type,
            period=period,
            user_id=user_id,
            period_start=period_start,
            period_end=period_end,
            status=ReportStatus.GENERATING,
        )
        self.db.add(report)
        await self.db.flush()

        try:
            # Collect data
            if report_type == ReportType.CLIENT:
                data = await self._collect_client_data(
                    user_id, period_start, period_end
                )
            else:
                data = await self._collect_owner_data(period_start, period_end)

            report.data = data

            # Generate AI summary
            summary = await self._generate_ai_summary(report_type, data)
            report.summary = summary

            # Render HTML
            html_content = self._render_html(report_type, data, summary)

            # In production: save to S3 and get signed URL
            # For now: store locally or in memory
            html_url = f"/reports/{report.id}.html"
            pdf_url = f"/reports/{report.id}.pdf"

            report.html_url = html_url
            report.pdf_url = pdf_url
            report.status = ReportStatus.COMPLETED
            report.generated_at = datetime.utcnow()

            await self.db.commit()
            logger.info(
                f"Report {report.id} generated successfully",
                extra={"report_id": report.id, "type": report_type, "period": period},
            )

            return report

        except Exception as e:
            report.status = ReportStatus.FAILED
            report.error_message = str(e)
            await self.db.commit()
            logger.error(
                f"Report generation failed: {e}",
                exc_info=True,
                extra={"report_id": report.id},
            )
            raise RuntimeError(f"Report generation failed: {e}") from e

    def _calculate_period_range(
        self, period: ReportPeriod
    ) -> tuple[datetime, datetime]:
        """Calculate start and end dates for report period."""
        now = datetime.utcnow()
        today = now.date()

        if period == ReportPeriod.DAILY:
            # Yesterday
            start = datetime.combine(today - timedelta(days=1), datetime.min.time())
            end = datetime.combine(today, datetime.min.time())
        elif period == ReportPeriod.WEEKLY:
            # Last 7 days
            start = datetime.combine(today - timedelta(days=7), datetime.min.time())
            end = datetime.combine(today, datetime.min.time())
        else:  # MONTHLY
            # Last 30 days
            start = datetime.combine(today - timedelta(days=30), datetime.min.time())
            end = datetime.combine(today, datetime.min.time())

        return start, end

    async def _collect_client_data(
        self, user_id: str, start: datetime, end: datetime
    ) -> dict[str, Any]:
        """Collect all data for client report."""
        # Get trades in period
        trades_result = await self.db.execute(
            select(Trade)
            .where(
                and_(
                    Trade.user_id == user_id,
                    Trade.closed_at >= start,
                    Trade.closed_at < end,
                )
            )
            .order_by(Trade.closed_at)
        )
        trades = trades_result.scalars().all()

        # Calculate metrics
        total_trades = len(trades)
        if total_trades == 0:
            # Zero trades edge case
            return {
                "total_trades": 0,
                "total_pnl": 0.0,
                "win_rate": 0.0,
                "sharpe_ratio": None,
                "best_trade": 0.0,
                "worst_trade": 0.0,
                "best_trade_date": None,
                "worst_trade_date": None,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "risk_reward": 0.0,
                "max_drawdown": 0.0,
                "current_equity": 0.0,
                "recovery_factor": 0.0,
                "top_instruments": [],
                "period_label": self._format_period_label(start, end),
            }

        total_pnl = sum(float(t.pnl or 0) for t in trades)
        wins = [t for t in trades if (t.pnl or 0) > 0]
        losses = [t for t in trades if (t.pnl or 0) < 0]
        win_rate = len(wins) / total_trades if total_trades > 0 else 0.0

        avg_win = sum(float(t.pnl) for t in wins) / len(wins) if wins else 0.0
        avg_loss = (
            abs(sum(float(t.pnl) for t in losses) / len(losses)) if losses else 0.0
        )
        risk_reward = avg_win / avg_loss if avg_loss > 0 else 0.0

        # Best/worst trades
        sorted_trades = sorted(trades, key=lambda t: float(t.pnl or 0))
        worst_trade = float(sorted_trades[0].pnl) if sorted_trades else 0.0
        worst_trade_date = (
            sorted_trades[0].closed_at.strftime("%Y-%m-%d") if sorted_trades else None
        )
        best_trade = float(sorted_trades[-1].pnl) if sorted_trades else 0.0
        best_trade_date = (
            sorted_trades[-1].closed_at.strftime("%Y-%m-%d") if sorted_trades else None
        )

        # Get equity metrics
        try:
            equity_series = await self.equity_engine.compute_equity_series(
                user_id, start, end
            )
            max_drawdown = float(equity_series.max_drawdown_percent) / 100.0
            current_equity = float(equity_series.final_equity)
            recovery_factor = (
                float(await self.equity_engine.get_recovery_factor(equity_series))
                if equity_series.max_drawdown > 0
                else 0.0
            )
        except Exception as e:
            logger.warning(f"Could not compute equity metrics: {e}")
            max_drawdown = 0.0
            current_equity = 0.0
            recovery_factor = 0.0

        # Get Sharpe ratio
        try:
            metrics = await self.metrics_engine.get_metrics_for_window(
                user_id, start, end
            )
            sharpe_ratio = float(metrics.get("sharpe_ratio", 0))
        except Exception:
            sharpe_ratio = None

        # Top instruments
        instrument_stats = {}
        for trade in trades:
            inst = trade.instrument
            if inst not in instrument_stats:
                instrument_stats[inst] = {
                    "name": inst,
                    "trades": 0,
                    "wins": 0,
                    "pnl": 0.0,
                }
            instrument_stats[inst]["trades"] += 1
            if (trade.pnl or 0) > 0:
                instrument_stats[inst]["wins"] += 1
            instrument_stats[inst]["pnl"] += float(trade.pnl or 0)

        top_instruments = sorted(
            [
                {
                    **stats,
                    "win_rate": (
                        stats["wins"] / stats["trades"] if stats["trades"] > 0 else 0.0
                    ),
                }
                for stats in instrument_stats.values()
            ],
            key=lambda x: x["pnl"],
            reverse=True,
        )[:5]

        return {
            "total_trades": total_trades,
            "total_pnl": total_pnl,
            "win_rate": win_rate,
            "sharpe_ratio": sharpe_ratio,
            "best_trade": best_trade,
            "worst_trade": worst_trade,
            "best_trade_date": best_trade_date,
            "worst_trade_date": worst_trade_date,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "risk_reward": risk_reward,
            "max_drawdown": max_drawdown,
            "current_equity": current_equity,
            "recovery_factor": recovery_factor,
            "top_instruments": top_instruments,
            "period_label": self._format_period_label(start, end),
        }

    async def _calculate_mrr(self) -> float:
        """Calculate Monthly Recurring Revenue (stub for PR-101)."""
        # TODO: Implement actual MRR calculation from subscriptions
        # For now, return mock data for testing
        users_result = await self.db.execute(
            select(User).where(User.tier != "free", User.suspended == False)
        )
        paid_users = users_result.scalars().all()

        # Estimate based on tier counts
        tier_prices = {"premium": 20.0, "pro": 50.0, "enterprise": 100.0}
        mrr = sum(tier_prices.get(u.tier, 0.0) for u in paid_users)
        return mrr

    async def _calculate_churn_rate(self) -> float:
        """Calculate churn rate (stub for PR-101)."""
        # TODO: Implement actual churn calculation
        # For now, return mock estimate
        return 0.03  # 3% monthly churn

    async def _collect_owner_data(
        self, start: datetime, end: datetime
    ) -> dict[str, Any]:
        """Collect all data for owner report."""
        # Revenue metrics
        mrr = await self._calculate_mrr()
        churn_rate = await self._calculate_churn_rate()

        # Previous period for comparison (stub)
        prev_start = start - (end - start)
        prev_mrr = mrr * 0.95  # Assume 5% growth for mock
        mrr_change = ((mrr - prev_mrr) / prev_mrr * 100) if prev_mrr > 0 else 0.0

        # Active users
        users_result = await self.db.execute(
            select(User).where(User.tier != "free", User.suspended == False)
        )
        active_users = len(users_result.scalars().all())

        # User growth
        new_users_result = await self.db.execute(
            select(User).where(
                and_(
                    User.created_at >= start, User.created_at < end, User.tier != "free"
                )
            )
        )
        user_growth = len(new_users_result.scalars().all())

        # ARPU
        arpu = mrr / active_users if active_users > 0 else 0.0

        # Revenue by tier
        revenue_by_tier = [
            {"name": "Standard", "subscribers": 50, "mrr": 1000, "percentage": 40.0},
            {"name": "Premium", "subscribers": 30, "mrr": 900, "percentage": 36.0},
            {"name": "Elite", "subscribers": 20, "mrr": 600, "percentage": 24.0},
        ]  # TODO: Calculate from real data

        # Platform performance
        all_trades_result = await self.db.execute(
            select(Trade).where(and_(Trade.closed_at >= start, Trade.closed_at < end))
        )
        all_trades = all_trades_result.scalars().all()

        total_signals = 0  # TODO: Count from signals table
        total_trades = len(all_trades)
        wins = sum(1 for t in all_trades if (t.pnl or 0) > 0)
        platform_win_rate = wins / total_trades if total_trades > 0 else 0.0
        avg_client_pnl = (
            sum(float(t.pnl or 0) for t in all_trades) / active_users
            if active_users > 0
            else 0.0
        )
        total_volume = sum(
            float(t.volume or 0) * float(t.entry_price or 0) for t in all_trades
        )

        # Incidents
        incidents_result = await self.db.execute(
            select(Incident).where(
                and_(Incident.opened_at >= start, Incident.opened_at < end)
            )
        )
        incidents = incidents_result.scalars().all()
        total_incidents = len(incidents)
        critical_incidents = sum(
            1 for i in incidents if i.severity == IncidentSeverity.CRITICAL
        )

        avg_resolution_time = "2.5 hours"  # TODO: Calculate from real data
        uptime = 0.9985  # TODO: Calculate from synthetics

        # Engagement metrics
        dau = active_users  # Simplified
        dau_change = 0.0
        approvals_per_user = 15.0  # TODO: Calculate
        approvals_change = 0.0
        education_completions = 50  # TODO: Calculate
        education_growth = 10
        support_tickets = 25  # TODO: Count from tickets
        ticket_change = -5

        # Churn risks
        churn_risks = []  # TODO: Identify from engagement patterns

        # Recommendations
        recommendations = [
            f"MRR grew {mrr_change:.1f}% this period. Focus on upselling Standard tier to Premium.",
            f"Platform win rate at {platform_win_rate*100:.1f}%. Consider strategy optimization.",
            f"Churn rate at {churn_rate*100:.1f}%. Target: below 5%.",
        ]

        return {
            "mrr": mrr,
            "mrr_change": mrr_change,
            "active_users": active_users,
            "user_growth": user_growth,
            "churn_rate": churn_rate,
            "arpu": arpu,
            "revenue_by_tier": revenue_by_tier,
            "total_signals": total_signals,
            "total_trades": total_trades,
            "platform_win_rate": platform_win_rate,
            "avg_client_pnl": avg_client_pnl,
            "total_volume": total_volume,
            "incidents": incidents,
            "total_incidents": total_incidents,
            "critical_incidents": critical_incidents,
            "avg_resolution_time": avg_resolution_time,
            "uptime": uptime,
            "dau": dau,
            "dau_change": dau_change,
            "approvals_per_user": approvals_per_user,
            "approvals_change": approvals_change,
            "education_completions": education_completions,
            "education_growth": education_growth,
            "support_tickets": support_tickets,
            "ticket_change": ticket_change,
            "churn_risks": churn_risks,
            "recommendations": recommendations,
            "period_label": self._format_period_label(start, end),
        }

    async def _generate_ai_summary(
        self, report_type: ReportType, data: dict[str, Any]
    ) -> str:
        """Generate AI narrative summary from data."""
        # In production: call OpenAI/Claude API
        # For now: template-based summary

        if report_type == ReportType.CLIENT:
            if data["total_trades"] == 0:
                return "No trades were executed during this period. Consider reviewing signal approvals to ensure you're actively participating in opportunities."

            pnl = data["total_pnl"]
            win_rate = data["win_rate"] * 100
            trades = data["total_trades"]

            if pnl > 0:
                sentiment = "strong positive"
            elif pnl < 0:
                sentiment = "negative"
            else:
                sentiment = "neutral"

            return (
                f"Your trading performance this period shows {sentiment} results with "
                f"£{pnl:,.2f} total P&L across {trades} trades. "
                f"Your win rate of {win_rate:.1f}% {'exceeded' if win_rate > 50 else 'was below'} "
                f"the 50% benchmark. "
                f"{'Risk management metrics look healthy.' if data['max_drawdown'] < 0.15 else 'Consider tightening risk controls to reduce drawdown.'}"
            )
        else:  # OWNER
            mrr = data["mrr"]
            mrr_change = data["mrr_change"]
            churn = data["churn_rate"] * 100
            users = data["active_users"]
            win_rate = data["platform_win_rate"] * 100

            return (
                f"Business performance this period: MRR at £{mrr:,.0f} "
                f"({'up' if mrr_change > 0 else 'down'} {abs(mrr_change):.1f}%), "
                f"serving {users} active users with {churn:.1f}% churn. "
                f"Platform win rate of {win_rate:.1f}% demonstrates strong signal quality. "
                f"{'Growth trajectory is positive.' if mrr_change > 0 else 'Focus on retention and upsell strategies.'}"
            )

    def _render_html(
        self, report_type: ReportType, data: dict[str, Any], summary: str
    ) -> str:
        """Render HTML from template."""
        template_name = (
            "client.html.j2" if report_type == ReportType.CLIENT else "owner.html.j2"
        )
        template = self.jinja_env.get_template(template_name)

        context = {
            **data,
            "ai_summary": summary,
            "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
            "app_url": "https://app.example.com/dashboard",
            "admin_url": "https://app.example.com/admin",
        }

        return template.render(context)

    def _format_period_label(self, start: datetime, end: datetime) -> str:
        """Format period label for display."""
        return f"{start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}"
