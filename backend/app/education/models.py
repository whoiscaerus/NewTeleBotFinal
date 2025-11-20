"""Education content models.

Course: Top-level container for educational content
Lesson: Individual lessons within a course
Quiz: Assessment associated with a lesson
QuizQuestion: Individual questions within a quiz
Attempt: User's quiz attempt with score and timestamp
Reward: Discount/credit issued for course completion

PR-064 Implementation.
"""

import enum
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, Boolean, CheckConstraint, Column, DateTime
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import relationship

from backend.app.core.db import Base


class CourseStatus(str, enum.Enum):
    """Course publication status."""

    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class Course(Base):
    """Educational course model.

    Represents a micro-course with multiple lessons and quizzes.
    Tracks enrollment, completion, and associated rewards.
    """

    __tablename__ = "courses"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    title = Column(String(200), nullable=False, index=True)
    description = Column(String(2000), nullable=False)
    status: Column[CourseStatus] = Column(
        SQLEnum(CourseStatus, name="course_status_enum"),
        nullable=False,
        default=CourseStatus.DRAFT,
        index=True,
    )
    duration_minutes = Column(Integer, nullable=False)  # Estimated completion time
    difficulty_level = Column(
        Integer, nullable=False, default=1
    )  # 1=beginner, 2=intermediate, 3=advanced
    reward_percent = Column(
        Float, nullable=True
    )  # Discount % for completion (e.g., 10.0 = 10%)
    reward_expires_days = Column(
        Integer, nullable=True, default=30
    )  # Reward validity period
    order_index = Column(Integer, nullable=False, default=0)  # Display order
    thumbnail_url = Column(String(500), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    # Relationships
    lessons = relationship(
        "Lesson", back_populates="course", cascade="all, delete-orphan"
    )
    attempts = relationship(
        "Attempt", back_populates="course", cascade="all, delete-orphan"
    )
    rewards = relationship(
        "Reward", back_populates="course", cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (
        Index("ix_courses_status_order", "status", "order_index"),
        CheckConstraint(
            "difficulty_level BETWEEN 1 AND 3", name="check_difficulty_range"
        ),
        CheckConstraint("duration_minutes > 0", name="check_duration_positive"),
        CheckConstraint(
            "reward_percent IS NULL OR (reward_percent >= 0 AND reward_percent <= 100)",
            name="check_reward_percent_range",
        ),
    )

    def __repr__(self) -> str:
        return f"<Course {self.id}: {self.title} ({self.status.value})>"


class Lesson(Base):
    """Lesson within a course.

    Individual lesson with content, quiz, and progress tracking.
    """

    __tablename__ = "lessons"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    course_id = Column(
        String(36),
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(String(200), nullable=False)
    content = Column(String(50000), nullable=False)  # Markdown content
    order_index = Column(Integer, nullable=False, default=0)
    duration_minutes = Column(Integer, nullable=False, default=5)
    is_required = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    # Relationships
    course = relationship("Course", back_populates="lessons")
    quizzes = relationship(
        "Quiz", back_populates="lesson", cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (
        Index("ix_lessons_course_order", "course_id", "order_index"),
        CheckConstraint("duration_minutes > 0", name="check_lesson_duration_positive"),
    )

    def __repr__(self) -> str:
        return f"<Lesson {self.id}: {self.title}>"


class Quiz(Base):
    """Quiz assessment for a lesson.

    Contains questions and tracks passing threshold.
    """

    __tablename__ = "quizzes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    lesson_id = Column(
        String(36),
        ForeignKey("lessons.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(String(200), nullable=False)
    description = Column(String(1000), nullable=True)
    passing_score = Column(Float, nullable=False, default=70.0)  # Minimum % to pass
    max_attempts = Column(Integer, nullable=True)  # None = unlimited
    retry_delay_minutes = Column(
        Integer, nullable=False, default=0
    )  # Rate limit between attempts
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    # Relationships
    lesson = relationship("Lesson", back_populates="quizzes")
    questions = relationship(
        "QuizQuestion", back_populates="quiz", cascade="all, delete-orphan"
    )
    attempts = relationship(
        "Attempt", back_populates="quiz", cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (
        CheckConstraint(
            "passing_score >= 0 AND passing_score <= 100",
            name="check_passing_score_range",
        ),
        CheckConstraint(
            "max_attempts IS NULL OR max_attempts > 0",
            name="check_max_attempts_positive",
        ),
        CheckConstraint("retry_delay_minutes >= 0", name="check_retry_delay_positive"),
    )

    def __repr__(self) -> str:
        return f"<Quiz {self.id}: {self.title}>"


class QuizQuestion(Base):
    """Individual question in a quiz.

    Supports multiple choice with single or multiple correct answers.
    """

    __tablename__ = "quiz_questions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    quiz_id = Column(
        String(36),
        ForeignKey("quizzes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_text = Column(String(1000), nullable=False)
    options = Column(JSON, nullable=False)  # List[str] - answer choices
    correct_answers = Column(
        JSON, nullable=False
    )  # List[int] - indices of correct options
    explanation = Column(String(2000), nullable=True)  # Shown after answering
    order_index = Column(Integer, nullable=False, default=0)
    points = Column(Integer, nullable=False, default=1)  # Weight for scoring
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    # Relationships
    quiz = relationship("Quiz", back_populates="questions")

    # Indexes
    __table_args__ = (
        Index("ix_quiz_questions_quiz_order", "quiz_id", "order_index"),
        CheckConstraint("points > 0", name="check_points_positive"),
    )

    def __repr__(self) -> str:
        return f"<QuizQuestion {self.id}: {self.question_text[:50]}...>"


class Attempt(Base):
    """User's quiz attempt record.

    Tracks answers, score, pass/fail status, and timestamp.
    Used for progress tracking and rate limiting.
    """

    __tablename__ = "attempts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(36), nullable=False, index=True)  # FK to users table
    course_id = Column(
        String(36),
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    quiz_id = Column(
        String(36),
        ForeignKey("quizzes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    answers = Column(
        JSON, nullable=False
    )  # Dict[question_id, List[int]] - user's answers
    score = Column(Float, nullable=False)  # Percentage score 0-100
    passed = Column(Boolean, nullable=False)
    time_taken_seconds = Column(Integer, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    # Relationships
    course = relationship("Course", back_populates="attempts")
    quiz = relationship("Quiz", back_populates="attempts")

    # Indexes
    __table_args__ = (
        Index("ix_attempts_user_course", "user_id", "course_id"),
        Index("ix_attempts_user_quiz_created", "user_id", "quiz_id", "created_at"),
        CheckConstraint("score >= 0 AND score <= 100", name="check_score_range"),
        CheckConstraint(
            "time_taken_seconds IS NULL OR time_taken_seconds > 0",
            name="check_time_taken_positive",
        ),
    )

    def __repr__(self) -> str:
        return f"<Attempt {self.id}: user={self.user_id} quiz={self.quiz_id} score={self.score}% passed={self.passed}>"


class Reward(Base):
    """Discount/credit reward for course completion.

    Issued when user completes a course with all required lessons passed.
    Tracks redemption status and expiration.
    """

    __tablename__ = "rewards"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(36), nullable=False, index=True)
    course_id = Column(
        String(36),
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reward_type = Column(
        String(50), nullable=False, default="discount"
    )  # 'discount' or 'credit'
    reward_value = Column(Float, nullable=False)  # Discount % or credit amount
    currency = Column(String(3), nullable=True)  # For credit rewards (GBP, USD, etc)
    issued_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    expires_at = Column(DateTime(timezone=True), nullable=False)
    redeemed_at = Column(DateTime(timezone=True), nullable=True)
    redemption_order_id = Column(String(100), nullable=True)  # Link to billing order

    # Relationships
    course = relationship("Course", back_populates="rewards")

    # Indexes
    __table_args__ = (
        Index("ix_rewards_user_issued", "user_id", "issued_at"),
        Index("ix_rewards_user_expires", "user_id", "expires_at"),
        Index("ix_rewards_user_course", "user_id", "course_id"),
        CheckConstraint("reward_value > 0", name="check_reward_value_positive"),
    )

    def __repr__(self) -> str:
        status = "redeemed" if self.redeemed_at else "active"
        return f"<Reward {self.id}: user={self.user_id} {self.reward_type}={self.reward_value} {status}>"
