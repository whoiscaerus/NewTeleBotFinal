"""Add CRM playbooks and automation tables (PR-098).

Revision ID: 098_crm_playbooks
Revises: 097_upsell_engine
Create Date: 2024-11-01 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "098_crm_playbooks"
down_revision = "097_upsell_engine"
branch_labels = None
depends_on = None


def upgrade():
    """Create CRM playbook execution tables."""

    # CRM Playbook Executions table
    op.create_table(
        "crm_playbook_executions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("playbook_name", sa.String(100), nullable=False, index=True),
        sa.Column("trigger_event", sa.String(100), nullable=False),
        sa.Column("context", JSONB, nullable=True),
        sa.Column(
            "status", sa.String(50), nullable=False, default="active", index=True
        ),
        sa.Column("current_step", sa.Integer, nullable=False, default=0),
        sa.Column("total_steps", sa.Integer, nullable=False),
        sa.Column("next_action_at", sa.DateTime, nullable=True, index=True),
        sa.Column("converted_at", sa.DateTime, nullable=True),
        sa.Column("conversion_value", sa.Integer, nullable=True),
        sa.Column(
            "created_at", sa.DateTime, nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )

    # Composite indexes for efficient queries
    op.create_index(
        "ix_crm_playbook_executions_user_status",
        "crm_playbook_executions",
        ["user_id", "status"],
    )
    op.create_index(
        "ix_crm_playbook_executions_playbook_status",
        "crm_playbook_executions",
        ["playbook_name", "status"],
    )

    # CRM Step Executions table (individual step tracking)
    op.create_table(
        "crm_step_executions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "execution_id",
            sa.String(36),
            sa.ForeignKey("crm_playbook_executions.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("step_number", sa.Integer, nullable=False),
        sa.Column("step_type", sa.String(50), nullable=False),
        sa.Column("config", JSONB, nullable=True),
        sa.Column("status", sa.String(50), nullable=False, default="pending"),
        sa.Column("message_id", sa.String(36), nullable=True),
        sa.Column("delivered_at", sa.DateTime, nullable=True),
        sa.Column("opened_at", sa.DateTime, nullable=True),
        sa.Column("clicked_at", sa.DateTime, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("executed_at", sa.DateTime, nullable=True),
        sa.Column(
            "created_at", sa.DateTime, nullable=False, server_default=sa.func.now()
        ),
    )

    # CRM Discount Codes table (one-time codes for rescue/winback)
    op.create_table(
        "crm_discount_codes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(50), nullable=False, unique=True, index=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "execution_id",
            sa.String(36),
            sa.ForeignKey("crm_playbook_executions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("percent_off", sa.Integer, nullable=False),
        sa.Column("max_uses", sa.Integer, nullable=False, default=1),
        sa.Column("used_count", sa.Integer, nullable=False, default=0),
        sa.Column("expires_at", sa.DateTime, nullable=False, index=True),
        sa.Column("used_at", sa.DateTime, nullable=True),
        sa.Column(
            "created_at", sa.DateTime, nullable=False, server_default=sa.func.now()
        ),
    )

    # Composite index for active discount code lookups
    op.create_index(
        "ix_crm_discount_codes_user_expires",
        "crm_discount_codes",
        ["user_id", "expires_at"],
    )
    op.create_index(
        "ix_crm_discount_codes_expires_used",
        "crm_discount_codes",
        ["expires_at", "used_count"],
    )


def downgrade():
    """Drop CRM playbook tables."""
    op.drop_table("crm_discount_codes")
    op.drop_table("crm_step_executions")
    op.drop_table("crm_playbook_executions")
