"""Add education tables for PR-064.

Revision ID: 064_education_tables
Revises: 015_add_close_commands
Create Date: 2025-01-26

Tables:
- courses: Educational courses with rewards
- lessons: Lessons within courses
- quizzes: Assessments for lessons
- quiz_questions: Questions within quizzes
- attempts: User quiz attempts with scores
- rewards: Discount/credit rewards for completion

PR-064 Implementation.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSON

# revision identifiers, used by Alembic.
revision = "064_education_tables"
down_revision = "015_add_close_commands"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create education tables."""

    # Create course_status enum
    op.execute(
        """
        CREATE TYPE course_status_enum AS ENUM ('draft', 'published', 'archived')
        """
    )

    # Create courses table
    op.create_table(
        "courses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False, index=True),
        sa.Column("description", sa.String(2000), nullable=False),
        sa.Column(
            "status",
            sa.Enum("draft", "published", "archived", name="course_status_enum"),
            nullable=False,
            index=True,
        ),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("difficulty_level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("reward_percent", sa.Float(), nullable=True),
        sa.Column(
            "reward_expires_days", sa.Integer(), nullable=True, server_default="30"
        ),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("thumbnail_url", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "difficulty_level BETWEEN 1 AND 3", name="check_difficulty_range"
        ),
        sa.CheckConstraint("duration_minutes > 0", name="check_duration_positive"),
        sa.CheckConstraint(
            "reward_percent IS NULL OR (reward_percent >= 0 AND reward_percent <= 100)",
            name="check_reward_percent_range",
        ),
    )

    # Create index on status + order_index
    op.create_index(
        "ix_courses_status_order",
        "courses",
        ["status", "order_index"],
    )

    # Create lessons table
    op.create_table(
        "lessons",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("course_id", sa.String(36), nullable=False, index=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("content", sa.String(50000), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "duration_minutes > 0", name="check_lesson_duration_positive"
        ),
    )

    # Create index on course_id + order_index
    op.create_index(
        "ix_lessons_course_order",
        "lessons",
        ["course_id", "order_index"],
    )

    # Create quizzes table
    op.create_table(
        "quizzes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("lesson_id", sa.String(36), nullable=False, index=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.String(1000), nullable=True),
        sa.Column("passing_score", sa.Float(), nullable=False, server_default="70.0"),
        sa.Column("max_attempts", sa.Integer(), nullable=True),
        sa.Column(
            "retry_delay_minutes", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "passing_score >= 0 AND passing_score <= 100",
            name="check_passing_score_range",
        ),
        sa.CheckConstraint(
            "max_attempts IS NULL OR max_attempts > 0",
            name="check_max_attempts_positive",
        ),
        sa.CheckConstraint(
            "retry_delay_minutes >= 0", name="check_retry_delay_positive"
        ),
    )

    # Create quiz_questions table
    op.create_table(
        "quiz_questions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("quiz_id", sa.String(36), nullable=False, index=True),
        sa.Column("question_text", sa.String(1000), nullable=False),
        sa.Column("options", JSON, nullable=False),
        sa.Column("correct_answers", JSON, nullable=False),
        sa.Column("explanation", sa.String(2000), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("points", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(["quiz_id"], ["quizzes.id"], ondelete="CASCADE"),
        sa.CheckConstraint("points > 0", name="check_points_positive"),
    )

    # Create index on quiz_id + order_index
    op.create_index(
        "ix_quiz_questions_quiz_order",
        "quiz_questions",
        ["quiz_id", "order_index"],
    )

    # Create attempts table
    op.create_table(
        "attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False, index=True),
        sa.Column("course_id", sa.String(36), nullable=False, index=True),
        sa.Column("quiz_id", sa.String(36), nullable=False, index=True),
        sa.Column("answers", JSON, nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("time_taken_seconds", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["quiz_id"], ["quizzes.id"], ondelete="CASCADE"),
        sa.CheckConstraint("score >= 0 AND score <= 100", name="check_score_range"),
        sa.CheckConstraint(
            "time_taken_seconds IS NULL OR time_taken_seconds > 0",
            name="check_time_taken_positive",
        ),
    )

    # Create indexes for attempts
    op.create_index(
        "ix_attempts_user_course",
        "attempts",
        ["user_id", "course_id"],
    )

    op.create_index(
        "ix_attempts_user_quiz_created",
        "attempts",
        ["user_id", "quiz_id", "created_at"],
    )

    # Create rewards table
    op.create_table(
        "rewards",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False, index=True),
        sa.Column("course_id", sa.String(36), nullable=False, index=True),
        sa.Column(
            "reward_type", sa.String(50), nullable=False, server_default="discount"
        ),
        sa.Column("reward_value", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("redemption_order_id", sa.String(100), nullable=True),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.CheckConstraint("reward_value > 0", name="check_reward_value_positive"),
    )

    # Create indexes for rewards
    op.create_index(
        "ix_rewards_user_issued",
        "rewards",
        ["user_id", "issued_at"],
    )

    op.create_index(
        "ix_rewards_user_expires",
        "rewards",
        ["user_id", "expires_at"],
    )

    op.create_index(
        "ix_rewards_user_course",
        "rewards",
        ["user_id", "course_id"],
    )


def downgrade() -> None:
    """Drop education tables."""

    # Drop tables in reverse order (due to foreign keys)
    op.drop_table("rewards")
    op.drop_table("attempts")
    op.drop_table("quiz_questions")
    op.drop_table("quizzes")
    op.drop_table("lessons")
    op.drop_table("courses")

    # Drop enum type
    op.execute("DROP TYPE course_status_enum")
