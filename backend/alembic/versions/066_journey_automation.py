"""PR-066: Journey automation tables

Revision ID: 066_journey_automation
Revises: 065_smart_alert_rules
Create Date: 2024-12-08
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "066_journey_automation"
down_revision = "065_smart_alert_rules"
branch_labels = None
depends_on = None


def upgrade():
    """Create journey automation tables."""
    # journeys table
    op.create_table(
        "journeys",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("trigger_type", sa.String(50), nullable=False),
        sa.Column("trigger_config", sa.JSON, nullable=False, default={}),
        sa.Column("is_active", sa.Boolean, nullable=False, default=True),
        sa.Column("priority", sa.Integer, nullable=False, default=0),
        sa.Column(
            "created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    op.create_index("ix_journeys_name", "journeys", ["name"])
    op.create_index("ix_journeys_trigger_type", "journeys", ["trigger_type"])
    op.create_index("ix_journeys_is_active", "journeys", ["is_active"])
    op.create_index(
        "ix_journeys_active_trigger", "journeys", ["is_active", "trigger_type"]
    )
    op.create_index("ix_journeys_priority", "journeys", ["priority"])

    # journey_steps table
    op.create_table(
        "journey_steps",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "journey_id",
            sa.String(36),
            sa.ForeignKey("journeys.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("order", sa.Integer, nullable=False),
        sa.Column("action_type", sa.String(50), nullable=False),
        sa.Column("action_config", sa.JSON, nullable=False, default={}),
        sa.Column("delay_minutes", sa.Integer, nullable=False, default=0),
        sa.Column("condition", sa.JSON, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, default=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    op.create_index("ix_journey_steps_journey_id", "journey_steps", ["journey_id"])
    op.create_index(
        "ix_journey_steps_journey_order", "journey_steps", ["journey_id", "order"]
    )

    # user_journeys table
    op.create_table(
        "user_journeys",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "journey_id",
            sa.String(36),
            sa.ForeignKey("journeys.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False, default="active"),
        sa.Column(
            "current_step_id",
            sa.String(36),
            sa.ForeignKey("journey_steps.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("started_at", sa.DateTime, nullable=False),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("failed_at", sa.DateTime, nullable=True),
        sa.Column("failure_reason", sa.Text, nullable=True),
        sa.Column("metadata", sa.JSON, nullable=False, default={}),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    op.create_index("ix_user_journeys_user_id", "user_journeys", ["user_id"])
    op.create_index("ix_user_journeys_journey_id", "user_journeys", ["journey_id"])
    op.create_index(
        "ix_user_journeys_user_journey",
        "user_journeys",
        ["user_id", "journey_id"],
        unique=True,
    )
    op.create_index("ix_user_journeys_started_at", "user_journeys", ["started_at"])
    op.create_index(
        "ix_user_journeys_status_started", "user_journeys", ["status", "started_at"]
    )

    # step_executions table
    op.create_table(
        "step_executions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_journey_id",
            sa.String(36),
            sa.ForeignKey("user_journeys.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "step_id",
            sa.String(36),
            sa.ForeignKey("journey_steps.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False, default="pending"),
        sa.Column("executed_at", sa.DateTime, nullable=False),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("result", sa.JSON, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("retry_count", sa.Integer, nullable=False, default=0),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    op.create_index(
        "ix_step_executions_user_journey_id", "step_executions", ["user_journey_id"]
    )
    op.create_index("ix_step_executions_step_id", "step_executions", ["step_id"])
    op.create_index(
        "ix_step_executions_executed_at", "step_executions", ["executed_at"]
    )
    op.create_index(
        "ix_step_executions_status_executed",
        "step_executions",
        ["status", "executed_at"],
    )
    op.create_index(
        "ix_step_executions_user_journey_step",
        "step_executions",
        ["user_journey_id", "step_id"],
    )


def downgrade():
    """Drop journey automation tables."""
    op.drop_index("ix_step_executions_user_journey_step", "step_executions")
    op.drop_index("ix_step_executions_status_executed", "step_executions")
    op.drop_index("ix_step_executions_executed_at", "step_executions")
    op.drop_index("ix_step_executions_step_id", "step_executions")
    op.drop_index("ix_step_executions_user_journey_id", "step_executions")
    op.drop_table("step_executions")

    op.drop_index("ix_user_journeys_status_started", "user_journeys")
    op.drop_index("ix_user_journeys_started_at", "user_journeys")
    op.drop_index("ix_user_journeys_user_journey", "user_journeys")
    op.drop_index("ix_user_journeys_journey_id", "user_journeys")
    op.drop_index("ix_user_journeys_user_id", "user_journeys")
    op.drop_table("user_journeys")

    op.drop_index("ix_journey_steps_journey_order", "journey_steps")
    op.drop_index("ix_journey_steps_journey_id", "journey_steps")
    op.drop_table("journey_steps")

    op.drop_index("ix_journeys_priority", "journeys")
    op.drop_index("ix_journeys_active_trigger", "journeys")
    op.drop_index("ix_journeys_is_active", "journeys")
    op.drop_index("ix_journeys_trigger_type", "journeys")
    op.drop_index("ix_journeys_name", "journeys")
    op.drop_table("journeys")
