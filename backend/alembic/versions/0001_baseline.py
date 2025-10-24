"""Baseline migration - initial database setup.

Revision ID: 0001_baseline
Revises: 
Create Date: 2024-01-01 00:00:00.000000

This baseline migration marks the starting point of database versioning.
Subsequent PRs will build schema incrementally on top of this baseline.
"""

# revision identifiers, used by Alembic.
revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade database schema.

    Baseline migration - no schema changes (tables created via SQLAlchemy ORM).
    """
    pass


def downgrade() -> None:
    """Downgrade database schema.

    Baseline migration - no schema changes to reverse.
    """
    pass
