"""
Report generation scheduler (PR-101).

Runs periodic report generation jobs (daily/weekly/monthly).
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.db import get_db
from backend.app.messaging.senders import send_email, send_telegram
from backend.app.reports.generator import ReportGenerator
from backend.app.reports.models import Report, ReportPeriod, ReportType
from backend.app.auth.models import User

logger = logging.getLogger(__name__)


class ReportsRunner:
    """
    Scheduler for automated report generation and delivery (PR-101).

    Runs daily/weekly/monthly jobs to generate and send reports.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.generator = ReportGenerator(db)

    async def run_daily_reports(self):
        """Generate and send daily reports for all eligible users."""
        logger.info("Starting daily reports generation")

        try:
            # Get users opted-in for daily reports
            users_result = await self.db.execute(
                select(User).where(
                    User.tier != "free",
                    User.suspended == False,
                    # TODO: Add preferences check for daily reports opt-in
                )
            )
            users = users_result.scalars().all()

            for user in users:
                try:
                    report = await self.generator.build_report(
                        ReportPeriod.DAILY, ReportType.CLIENT, user_id=user.id
                    )
                    await self._deliver_report(report, user)
                except Exception as e:
                    logger.error(
                        f"Failed to generate daily report for user {user.id}: {e}",
                        exc_info=True,
                    )

            logger.info(f"Daily reports completed: {len(users)} users processed")

        except Exception as e:
            logger.error(f"Daily reports job failed: {e}", exc_info=True)

    async def run_weekly_reports(self):
        """Generate and send weekly reports."""
        logger.info("Starting weekly reports generation")

        try:
            users_result = await self.db.execute(
                select(User).where(User.tier != "free", User.suspended == False)
            )
            users = users_result.scalars().all()

            for user in users:
                try:
                    report = await self.generator.build_report(
                        ReportPeriod.WEEKLY, ReportType.CLIENT, user_id=user.id
                    )
                    await self._deliver_report(report, user)
                except Exception as e:
                    logger.error(
                        f"Failed to generate weekly report for user {user.id}: {e}",
                        exc_info=True,
                    )

            logger.info(f"Weekly reports completed: {len(users)} users processed")

        except Exception as e:
            logger.error(f"Weekly reports job failed: {e}", exc_info=True)

    async def run_monthly_reports(self):
        """Generate and send monthly reports."""
        logger.info("Starting monthly reports generation")

        try:
            # Client reports
            users_result = await self.db.execute(
                select(User).where(User.tier != "free", User.suspended == False)
            )
            users = users_result.scalars().all()

            for user in users:
                try:
                    report = await self.generator.build_report(
                        ReportPeriod.MONTHLY, ReportType.CLIENT, user_id=user.id
                    )
                    await self._deliver_report(report, user)
                except Exception as e:
                    logger.error(
                        f"Failed to generate monthly report for user {user.id}: {e}",
                        exc_info=True,
                    )

            # Owner report
            try:
                owner_report = await self.generator.build_report(
                    ReportPeriod.MONTHLY, ReportType.OWNER
                )
                await self._deliver_owner_report(owner_report)
            except Exception as e:
                logger.error(f"Failed to generate owner report: {e}", exc_info=True)

            logger.info(
                f"Monthly reports completed: {len(users)} client + 1 owner reports"
            )

        except Exception as e:
            logger.error(f"Monthly reports job failed: {e}", exc_info=True)

    async def _deliver_report(self, report: Report, user: User):
        """Deliver report to user via configured channels."""
        delivered_channels = []
        failed_channels = []

        # Email delivery
        try:
            await send_email(
                to=user.email,
                subject=f"Your {report.period.value} Trading Report",
                html_content=f"""
                <p>Hi {user.telegram_username or 'there'},</p>
                <p>Your {report.period.value} trading report is ready!</p>
                <p><strong>Summary:</strong> {report.summary}</p>
                <p><a href="{report.html_url}">View Full Report</a> |
                   <a href="{report.pdf_url}">Download PDF</a></p>
                """,
            )
            delivered_channels.append("email")
        except Exception as e:
            logger.error(f"Email delivery failed for report {report.id}: {e}")
            failed_channels.append("email")

        # Telegram delivery (if user has telegram_id)
        if user.telegram_id:
            try:
                await send_telegram(
                    user_id=user.telegram_id,
                    message=f"""
📊 *Your {report.period.value.title()} Trading Report*

{report.summary}

[View Report]({report.html_url})
[Download PDF]({report.pdf_url})
                    """,
                )
                delivered_channels.append("telegram")
            except Exception as e:
                logger.error(f"Telegram delivery failed for report {report.id}: {e}")
                failed_channels.append("telegram")

        # Update report delivery status
        report.delivered_channels = delivered_channels
        report.delivery_failed_channels = failed_channels
        await self.db.commit()

    async def _deliver_owner_report(self, report: Report):
        """Deliver owner report via email."""
        try:
            # TODO: Get owner email from config
            owner_email = "owner@example.com"

            await send_email(
                to=owner_email,
                subject=f"Business Summary Report - {report.period.value}",
                html_content=f"""
                <p><strong>Executive Summary:</strong> {report.summary}</p>
                <p><a href="{report.html_url}">View Full Report</a> |
                   <a href="{report.pdf_url}">Download PDF</a></p>
                <p><em>Confidential - Owner Only</em></p>
                """,
            )

            report.delivered_channels = ["email"]
            await self.db.commit()

        except Exception as e:
            logger.error(f"Owner report delivery failed: {e}", exc_info=True)
            report.delivery_failed_channels = ["email"]
            await self.db.commit()


# Entry points for scheduler (APScheduler, Celery, etc.)
async def run_daily_reports_job():
    """Entry point for daily reports cron job."""
    async for db in get_db():
        runner = ReportsRunner(db)
        await runner.run_daily_reports()


async def run_weekly_reports_job():
    """Entry point for weekly reports cron job."""
    async for db in get_db():
        runner = ReportsRunner(db)
        await runner.run_weekly_reports()


async def run_monthly_reports_job():
    """Entry point for monthly reports cron job."""
    async for db in get_db():
        runner = ReportsRunner(db)
        await runner.run_monthly_reports()
