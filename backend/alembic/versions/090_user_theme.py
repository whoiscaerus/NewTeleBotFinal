"""Add theme_preference to users table (PR-090)

Revision ID: 090_user_theme
Revises: 088_gamification
Create Date: 2025-11-10 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '090_user_theme'
down_revision = '088_gamification'
branch_labels = None
depends_on = None


def upgrade():
    """Add theme_preference column to users table."""
    # Add theme_preference column with default value
    op.add_column(
        'users',
        sa.Column(
            'theme_preference',
            sa.String(),
            nullable=True,  # Initially nullable for existing users
            comment='User theme preference: professional, darkTrader, or goldMinimal'
        )
    )

    # Set default for existing users
    op.execute("UPDATE users SET theme_preference = 'professional' WHERE theme_preference IS NULL")

    # Add index for theme analytics
    op.create_index(
        'ix_users_theme_preference',
        'users',
        ['theme_preference'],
        unique=False
    )


def downgrade():
    """Remove theme_preference column from users table."""
    op.drop_index('ix_users_theme_preference', table_name='users')
    op.drop_column('users', 'theme_preference')
