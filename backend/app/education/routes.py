"""Education API routes.

REST endpoints for course management, quiz attempts, and rewards.
Supports course listing, lesson retrieval, quiz submission, and progress tracking.

PR-064 Implementation.
"""

import logging
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from prometheus_client import Counter
from pydantic import BaseModel, Field, validator
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.dependencies import get_current_user
from backend.app.auth.models import User
from backend.app.core.db import get_db
from backend.app.education.models import CourseStatus
from backend.app.education.rewards import get_active_rewards
from backend.app.education.service import EducationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/education", tags=["education"])

# Prometheus metrics (PR-089)
quiz_pass_total = Counter(
    "education_quiz_pass_total",
    "Total quiz attempts that passed",
    ["quiz_id", "course_id"],
)

quiz_fail_total = Counter(
    "education_quiz_fail_total",
    "Total quiz attempts that failed",
    ["quiz_id", "course_id"],
)

lessons_completed_total = Counter(
    "education_lessons_completed_total",
    "Total lessons completed by users",
    ["course_id", "lesson_id"],
)

rewards_issued_total = Counter(
    "education_rewards_issued_total",
    "Total rewards issued",
    ["course_id", "reward_type"],
)


# Request/Response Schemas


class CourseOut(BaseModel):
    """Course response schema."""

    id: str
    title: str
    description: str
    status: str
    duration_minutes: int
    difficulty_level: int
    reward_percent: float | None = None
    reward_expires_days: int | None = None
    order_index: int
    thumbnail_url: str | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LessonOut(BaseModel):
    """Lesson response schema."""

    id: str
    course_id: str
    title: str
    content: str
    order_index: int
    duration_minutes: int
    is_required: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class QuizQuestionOut(BaseModel):
    """Quiz question response schema (without correct answers for active attempts)."""

    id: str
    question_text: str
    options: list[str]
    order_index: int
    points: int

    class Config:
        from_attributes = True


class QuizOut(BaseModel):
    """Quiz response schema."""

    id: str
    lesson_id: str
    title: str
    description: str | None
    passing_score: float
    max_attempts: int | None
    retry_delay_minutes: int
    questions: list[QuizQuestionOut]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AttemptSubmit(BaseModel):
    """Quiz attempt submission schema."""

    course_id: str = Field(..., description="Course UUID")
    quiz_id: str = Field(..., description="Quiz UUID")
    answers: dict[str, list[int]] = Field(
        ..., description="User answers: {question_id: [option_indices]}"
    )
    time_taken_seconds: int | None = Field(
        None, description="Time spent on quiz", ge=1
    )

    @validator("answers")
    def validate_answers(cls, v: dict[str, list[int]]) -> dict[str, list[int]]:
        """Validate answer format."""
        if not v:
            raise ValueError("Answers cannot be empty")
        for question_id, indices in v.items():
            if not isinstance(indices, list):
                raise ValueError(f"Answer for {question_id} must be a list of indices")
            if not all(isinstance(i, int) and i >= 0 for i in indices):
                raise ValueError(
                    f"Answer indices for {question_id} must be non-negative integers"
                )
        return v


class AttemptOut(BaseModel):
    """Quiz attempt response schema."""

    id: str
    user_id: str
    course_id: str
    quiz_id: str
    score: float
    passed: bool
    time_taken_seconds: int | None
    created_at: datetime
    grading_details: dict[str, Any] | None = None

    class Config:
        from_attributes = True


class RewardOut(BaseModel):
    """Reward response schema."""

    id: str
    user_id: str
    course_id: str
    reward_type: str
    reward_value: float
    currency: str | None
    issued_at: datetime
    expires_at: datetime
    redeemed_at: datetime | None
    redemption_order_id: str | None

    class Config:
        from_attributes = True


class ProgressOut(BaseModel):
    """User progress response schema."""

    course_id: str
    user_id: str
    completed: bool
    completion_details: dict[str, Any]
    total_attempts: int
    passed_attempts: int
    rewards: list[RewardOut]


# Routes


@router.get("/courses", response_model=list[CourseOut])
async def list_courses(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: str | None = None,
):
    """List all available courses.

    Args:
        status_filter: Filter by course status (draft/published/archived)
        current_user: Authenticated user
        db: Database session

    Returns:
        List of courses ordered by display order

    Example:
        GET /api/v1/education/courses
        GET /api/v1/education/courses?status_filter=published
    """
    service = EducationService(db)

    # Parse status filter
    course_status = None
    if status_filter:
        try:
            course_status = CourseStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_filter}. Must be draft/published/archived",
            )

    courses = await service.list_courses(status=course_status)

    logger.info(
        f"Listed courses: user={current_user.id} status={status_filter} count={len(courses)}",
        extra={
            "user_id": current_user.id,
            "status": status_filter,
            "count": len(courses),
        },
    )

    return courses


@router.get("/courses/{course_id}", response_model=CourseOut)
async def get_course(
    course_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get course by ID.

    Args:
        course_id: Course UUID
        current_user: Authenticated user
        db: Database session

    Returns:
        Course details

    Raises:
        HTTPException: 404 if course not found

    Example:
        GET /api/v1/education/courses/{course_id}
    """
    service = EducationService(db)
    course = await service.get_course(course_id)

    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Course not found: {course_id}",
        )

    return course


@router.get("/lessons/{lesson_id}", response_model=LessonOut)
async def get_lesson(
    lesson_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get lesson by ID.

    Args:
        lesson_id: Lesson UUID
        current_user: Authenticated user
        db: Database session

    Returns:
        Lesson details with content

    Raises:
        HTTPException: 404 if lesson not found

    Example:
        GET /api/v1/education/lessons/{lesson_id}
    """
    service = EducationService(db)
    lesson = await service.get_lesson(lesson_id)

    if not lesson:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lesson not found: {lesson_id}",
        )

    return lesson


@router.get("/quizzes/{quiz_id}", response_model=QuizOut)
async def get_quiz(
    quiz_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get quiz by ID with questions.

    Args:
        quiz_id: Quiz UUID
        current_user: Authenticated user
        db: Database session

    Returns:
        Quiz details with questions (correct answers hidden)

    Raises:
        HTTPException: 404 if quiz not found

    Example:
        GET /api/v1/education/quizzes/{quiz_id}
    """
    service = EducationService(db)
    quiz = await service.get_quiz(quiz_id)

    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quiz not found: {quiz_id}",
        )

    # Get questions
    questions = await service.get_quiz_questions(quiz_id)

    # Convert to response schema (without correct answers)
    quiz_out = QuizOut(
        id=quiz.id,
        lesson_id=quiz.lesson_id,
        title=quiz.title,
        description=quiz.description,
        passing_score=quiz.passing_score,
        max_attempts=quiz.max_attempts,
        retry_delay_minutes=quiz.retry_delay_minutes,
        questions=[
            QuizQuestionOut(
                id=q.id,
                question_text=q.question_text,
                options=q.options,
                order_index=q.order_index,
                points=q.points,
            )
            for q in questions
        ],
        created_at=quiz.created_at,
        updated_at=quiz.updated_at,
    )

    return quiz_out


@router.post(
    "/attempts", response_model=AttemptOut, status_code=status.HTTP_201_CREATED
)
async def submit_attempt(
    attempt_data: AttemptSubmit,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Submit a quiz attempt for grading.

    Args:
        attempt_data: Quiz attempt submission
        current_user: Authenticated user
        db: Database session

    Returns:
        Graded attempt with score and pass/fail status

    Raises:
        HTTPException: 400 if rate limited or max attempts reached
        HTTPException: 404 if quiz not found

    Example:
        POST /api/v1/education/attempts
        {
            "course_id": "course-uuid",
            "quiz_id": "quiz-uuid",
            "answers": {
                "question-1-uuid": [0, 2],
                "question-2-uuid": [1]
            },
            "time_taken_seconds": 180
        }
    """
    service = EducationService(db)

    try:
        attempt, grading_details = await service.submit_attempt(
            user_id=current_user.id,
            course_id=attempt_data.course_id,
            quiz_id=attempt_data.quiz_id,
            answers=attempt_data.answers,
            time_taken_seconds=attempt_data.time_taken_seconds,
        )

        # Update Prometheus metrics (PR-089)
        if attempt.passed:
            quiz_pass_total.labels(
                quiz_id=attempt_data.quiz_id,
                course_id=attempt_data.course_id,
            ).inc()

            # Lesson completion: passing quiz = completing lesson
            # Get lesson_id from quiz
            quiz = await service.get_quiz(attempt_data.quiz_id)
            if quiz:
                lessons_completed_total.labels(
                    course_id=attempt_data.course_id,
                    lesson_id=quiz.lesson_id,
                ).inc()
        else:
            quiz_fail_total.labels(
                quiz_id=attempt_data.quiz_id,
                course_id=attempt_data.course_id,
            ).inc()

        # Check course completion and issue reward if eligible
        completed, _ = await service.check_course_completion(
            current_user.id, attempt_data.course_id
        )

        if completed and attempt.passed:
            try:
                reward = await service.issue_course_reward(
                    current_user.id, attempt_data.course_id
                )
                if reward:
                    # Update Prometheus metric
                    rewards_issued_total.labels(
                        course_id=attempt_data.course_id,
                        reward_type=reward.reward_type,
                    ).inc()
            except ValueError as e:
                # Reward already issued or no reward configured
                logger.info(
                    f"Reward not issued: {e}",
                    extra={
                        "user_id": current_user.id,
                        "course_id": attempt_data.course_id,
                    },
                )

        # Return attempt with grading details
        attempt_out = AttemptOut(
            id=attempt.id,
            user_id=attempt.user_id,
            course_id=attempt.course_id,
            quiz_id=attempt.quiz_id,
            score=attempt.score,
            passed=attempt.passed,
            time_taken_seconds=attempt.time_taken_seconds,
            created_at=attempt.created_at,
            grading_details=grading_details,
        )

        logger.info(
            f"Attempt submitted: {attempt.id} user={current_user.id} quiz={attempt_data.quiz_id} score={attempt.score:.1f}% passed={attempt.passed}",
            extra={
                "attempt_id": attempt.id,
                "user_id": current_user.id,
                "quiz_id": attempt_data.quiz_id,
                "score": attempt.score,
                "passed": attempt.passed,
            },
        )

        return attempt_out

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/progress/{course_id}", response_model=ProgressOut)
async def get_progress(
    course_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get user's progress in a course.

    Args:
        course_id: Course UUID
        current_user: Authenticated user
        db: Database session

    Returns:
        Progress summary with completion status, attempts, and rewards

    Example:
        GET /api/v1/education/progress/{course_id}
    """
    service = EducationService(db)
    progress = await service.get_user_progress(current_user.id, course_id)

    # Convert rewards to response schema
    progress["rewards"] = [
        RewardOut(
            id=r.id,
            user_id=r.user_id,
            course_id=r.course_id,
            reward_type=r.reward_type,
            reward_value=r.reward_value,
            currency=r.currency,
            issued_at=r.issued_at,
            expires_at=r.expires_at,
            redeemed_at=r.redeemed_at,
            redemption_order_id=r.redemption_order_id,
        )
        for r in progress["rewards"]
    ]

    return ProgressOut(**progress)


@router.get("/rewards", response_model=list[RewardOut])
async def list_rewards(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    reward_type: str | None = None,
):
    """List user's active rewards.

    Args:
        reward_type: Filter by reward type (discount/credit) or None for all
        current_user: Authenticated user
        db: Database session

    Returns:
        List of active (unredeemed, unexpired) rewards

    Example:
        GET /api/v1/education/rewards
        GET /api/v1/education/rewards?reward_type=discount
    """
    rewards = await get_active_rewards(db, current_user.id, reward_type)

    logger.info(
        f"Listed rewards: user={current_user.id} type={reward_type} count={len(rewards)}",
        extra={
            "user_id": current_user.id,
            "reward_type": reward_type,
            "count": len(rewards),
        },
    )

    return rewards
