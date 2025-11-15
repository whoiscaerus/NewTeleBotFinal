"""Education service layer.

Business logic for course management, quiz attempts, grading, and progress tracking.
Handles rate limiting, validation, and reward issuance.

PR-064 Implementation.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from backend.app.education.models import (
    Attempt,
    Course,
    CourseStatus,
    Lesson,
    Quiz,
    QuizQuestion,
    Reward,
)
from backend.app.education.rewards import grant_discount

logger = logging.getLogger(__name__)


class EducationService:
    """Service for education content and quiz management."""

    def __init__(self, db: AsyncSession):
        """Initialize education service.

        Args:
            db: Database session
        """
        self.db = db

    async def list_courses(
        self,
        status: Optional[CourseStatus] = None,
        include_lessons: bool = False,
    ) -> list[Course]:
        """List all courses, optionally filtered by status.

        Args:
            status: Filter by course status (None = all published)
            include_lessons: Include lesson count/metadata

        Returns:
            List of courses ordered by order_index
        """
        query = select(Course)

        if status:
            query = query.where(Course.status == status)
        else:
            # Default: only published courses
            query = query.where(Course.status == CourseStatus.PUBLISHED)

        query = query.order_by(Course.order_index, Course.created_at)

        result = await self.db.execute(query)
        courses = list(result.scalars().all())

        logger.info(
            f"Listed {len(courses)} courses",
            extra={
                "status": status.value if status else "published",
                "count": len(courses),
            },
        )

        return courses

    async def get_course(self, course_id: str) -> Optional[Course]:
        """Get course by ID with lessons and quizzes.

        Args:
            course_id: Course UUID

        Returns:
            Course with relationships loaded, or None
        """
        result = await self.db.execute(select(Course).where(Course.id == course_id))
        course = result.scalar_one_or_none()

        if course:
            logger.debug(f"Retrieved course: {course_id}")

        return course

    async def get_lesson(self, lesson_id: str) -> Optional[Lesson]:
        """Get lesson by ID with quiz.

        Args:
            lesson_id: Lesson UUID

        Returns:
            Lesson with quiz loaded, or None
        """
        result = await self.db.execute(select(Lesson).where(Lesson.id == lesson_id))
        lesson = result.scalar_one_or_none()

        if lesson:
            logger.debug(f"Retrieved lesson: {lesson_id}")

        return lesson

    async def get_quiz(self, quiz_id: str) -> Optional[Quiz]:
        """Get quiz by ID with questions.

        Args:
            quiz_id: Quiz UUID

        Returns:
            Quiz with questions loaded, or None
        """
        result = await self.db.execute(select(Quiz).where(Quiz.id == quiz_id))
        quiz = result.scalar_one_or_none()

        if quiz:
            logger.debug(f"Retrieved quiz: {quiz_id}")

        return quiz

    async def get_quiz_questions(self, quiz_id: str) -> list[QuizQuestion]:
        """Get all questions for a quiz.

        Args:
            quiz_id: Quiz UUID

        Returns:
            List of questions ordered by order_index
        """
        result = await self.db.execute(
            select(QuizQuestion)
            .where(QuizQuestion.quiz_id == quiz_id)
            .order_by(QuizQuestion.order_index)
        )
        questions = list(result.scalars().all())

        return questions

    async def check_rate_limit(
        self, user_id: str, quiz_id: str, retry_delay_minutes: int
    ) -> tuple[bool, Optional[datetime]]:
        """Check if user can attempt quiz (rate limiting).

        Args:
            user_id: User UUID
            quiz_id: Quiz UUID
            retry_delay_minutes: Required delay between attempts

        Returns:
            Tuple of (can_attempt, available_at)
        """
        if retry_delay_minutes == 0:
            return True, None

        # Get last attempt
        result = await self.db.execute(
            select(Attempt)
            .where(
                and_(
                    Attempt.user_id == user_id,
                    Attempt.quiz_id == quiz_id,
                )
            )
            .order_by(Attempt.created_at.desc())
            .limit(1)
        )
        last_attempt = result.scalar_one_or_none()

        if not last_attempt:
            return True, None

        # Calculate when next attempt is available
        # Ensure created_at is aware before adding timedelta
        created_at = last_attempt.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)

        available_at = created_at + timedelta(minutes=retry_delay_minutes)
        now = datetime.now(UTC)

        if now < available_at:
            logger.warning(
                f"Rate limit: user {user_id} quiz {quiz_id} available at {available_at}",
                extra={
                    "user_id": user_id,
                    "quiz_id": quiz_id,
                    "available_at": available_at.isoformat(),
                },
            )
            return False, available_at

        return True, None

    async def check_max_attempts(
        self, user_id: str, quiz_id: str, max_attempts: Optional[int]
    ) -> tuple[bool, int]:
        """Check if user has remaining attempts.

        Args:
            user_id: User UUID
            quiz_id: Quiz UUID
            max_attempts: Maximum allowed attempts (None = unlimited)

        Returns:
            Tuple of (can_attempt, attempts_used)
        """
        if max_attempts is None:
            return True, 0

        # Count attempts
        result = await self.db.execute(
            select(func.count(Attempt.id)).where(
                and_(
                    Attempt.user_id == user_id,
                    Attempt.quiz_id == quiz_id,
                )
            )
        )
        attempts_used = result.scalar_one()

        if attempts_used >= max_attempts:
            logger.warning(
                f"Max attempts reached: user {user_id} quiz {quiz_id} ({attempts_used}/{max_attempts})",
                extra={
                    "user_id": user_id,
                    "quiz_id": quiz_id,
                    "attempts_used": attempts_used,
                    "max_attempts": max_attempts,
                },
            )
            return False, attempts_used

        return True, attempts_used

    async def grade_quiz(
        self, quiz: Quiz, questions: list[QuizQuestion], answers: dict[str, list[int]]
    ) -> tuple[float, bool, dict[str, Any]]:
        """Grade a quiz attempt.

        Args:
            quiz: Quiz being graded
            questions: All quiz questions
            answers: User's answers {question_id: [option_indices]}

        Returns:
            Tuple of (score_percent, passed, grading_details)
        """
        total_points = sum(q.points for q in questions)
        earned_points = 0
        question_results = []

        for question in questions:
            user_answer = answers.get(question.id, [])
            correct_answer = question.correct_answers

            # Check if answer matches (order doesn't matter for multi-select)
            is_correct = sorted(user_answer) == sorted(correct_answer)

            if is_correct:
                earned_points += question.points

            question_results.append(
                {
                    "question_id": question.id,
                    "correct": is_correct,
                    "user_answer": user_answer,
                    "correct_answer": correct_answer,
                    "points_earned": question.points if is_correct else 0,
                    "points_possible": question.points,
                }
            )

        # Calculate percentage score
        score_percent = (earned_points / total_points * 100) if total_points > 0 else 0
        passed = score_percent >= quiz.passing_score

        grading_details = {
            "total_points": total_points,
            "earned_points": earned_points,
            "score_percent": score_percent,
            "passing_score": quiz.passing_score,
            "passed": passed,
            "questions": question_results,
        }

        logger.info(
            f"Graded quiz: {quiz.id} score={score_percent:.1f}% passed={passed}",
            extra={"quiz_id": quiz.id, "score": score_percent, "passed": passed},
        )

        return score_percent, passed, grading_details

    async def submit_attempt(
        self,
        user_id: str,
        course_id: str,
        quiz_id: str,
        answers: dict[str, list[int]],
        time_taken_seconds: Optional[int] = None,
    ) -> tuple[Attempt, dict[str, Any]]:
        """Submit and grade a quiz attempt.

        Args:
            user_id: User UUID
            course_id: Course UUID
            quiz_id: Quiz UUID
            answers: User's answers {question_id: [option_indices]}
            time_taken_seconds: Time spent on quiz

        Returns:
            Tuple of (attempt_record, grading_details)

        Raises:
            ValueError: If rate limited, max attempts reached, or invalid quiz
        """
        # Get quiz with questions
        quiz = await self.get_quiz(quiz_id)
        if not quiz:
            raise ValueError(f"Quiz not found: {quiz_id}")

        questions = await self.get_quiz_questions(quiz_id)
        if not questions:
            raise ValueError(f"Quiz has no questions: {quiz_id}")

        # Check rate limit
        can_attempt, available_at = await self.check_rate_limit(
            user_id, quiz_id, quiz.retry_delay_minutes
        )
        if not can_attempt:
            raise ValueError(
                f"Rate limited. Next attempt available at {available_at.isoformat()}"
            )

        # Check max attempts
        can_attempt, attempts_used = await self.check_max_attempts(
            user_id, quiz_id, quiz.max_attempts
        )
        if not can_attempt:
            raise ValueError(
                f"Maximum attempts reached: {attempts_used}/{quiz.max_attempts}"
            )

        # Grade the quiz
        score, passed, grading_details = await self.grade_quiz(quiz, questions, answers)

        # Create attempt record
        attempt = Attempt(
            user_id=user_id,
            course_id=course_id,
            quiz_id=quiz_id,
            answers=answers,
            score=score,
            passed=passed,
            time_taken_seconds=time_taken_seconds,
        )

        self.db.add(attempt)
        await self.db.commit()
        await self.db.refresh(attempt)

        logger.info(
            f"Attempt submitted: {attempt.id} user={user_id} quiz={quiz_id} score={score:.1f}% passed={passed}",
            extra={
                "attempt_id": attempt.id,
                "user_id": user_id,
                "quiz_id": quiz_id,
                "score": score,
                "passed": passed,
            },
        )

        return attempt, grading_details

    async def check_course_completion(
        self, user_id: str, course_id: str
    ) -> tuple[bool, dict[str, Any]]:
        """Check if user has completed all required lessons in a course.

        Args:
            user_id: User UUID
            course_id: Course UUID

        Returns:
            Tuple of (completed, completion_details)
        """
        # Get course with lessons
        course = await self.get_course(course_id)
        if not course:
            raise ValueError(f"Course not found: {course_id}")

        # Get all required lessons
        result = await self.db.execute(
            select(Lesson).where(
                and_(
                    Lesson.course_id == course_id,
                    Lesson.is_required == True,  # noqa: E712
                )
            )
        )
        required_lessons = list(result.scalars().all())

        if not required_lessons:
            # No required lessons = course complete
            return True, {
                "required_lessons": 0,
                "completed_lessons": 0,
                "completion_rate": 100.0,
            }

        # Check which lessons have passed quiz attempts
        completed_lessons = []
        for lesson in required_lessons:
            # Get quizzes for this lesson
            result = await self.db.execute(
                select(Quiz).where(Quiz.lesson_id == lesson.id)
            )
            quizzes = list(result.scalars().all())

            if not quizzes:
                # No quiz = lesson considered complete
                completed_lessons.append(lesson.id)
                continue

            # Check if user has passed any quiz for this lesson
            for quiz in quizzes:
                result = await self.db.execute(
                    select(Attempt)
                    .where(
                        and_(
                            Attempt.user_id == user_id,
                            Attempt.quiz_id == quiz.id,
                            Attempt.passed == True,  # noqa: E712
                        )
                    )
                    .limit(1)
                )
                passed_attempt = result.scalar_one_or_none()

                if passed_attempt:
                    completed_lessons.append(lesson.id)
                    break

        completion_rate = len(completed_lessons) / len(required_lessons) * 100
        completed = len(completed_lessons) == len(required_lessons)

        completion_details = {
            "required_lessons": len(required_lessons),
            "completed_lessons": len(completed_lessons),
            "completion_rate": completion_rate,
            "completed": completed,
        }

        logger.info(
            f"Course completion check: user={user_id} course={course_id} completed={completed} rate={completion_rate:.1f}%",
            extra={
                "user_id": user_id,
                "course_id": course_id,
                "completed": completed,
                "completion_rate": completion_rate,
            },
        )

        return completed, completion_details

    async def issue_course_reward(
        self, user_id: str, course_id: str
    ) -> Optional[Reward]:
        """Issue reward for course completion if eligible.

        Args:
            user_id: User UUID
            course_id: Course UUID

        Returns:
            Reward record if issued, None if not eligible or already issued

        Raises:
            ValueError: If course not found or not completed
        """
        # Check course completion
        completed, _ = await self.check_course_completion(user_id, course_id)
        if not completed:
            raise ValueError(f"Course not completed: {course_id}")

        # Get course
        course = await self.get_course(course_id)
        if not course:
            raise ValueError(f"Course not found: {course_id}")

        # Check if course has reward configured
        if not course.reward_percent:
            logger.info(f"No reward configured for course: {course_id}")
            return None

        # Check if reward already issued
        result = await self.db.execute(
            select(Reward)
            .where(
                and_(
                    Reward.user_id == user_id,
                    Reward.course_id == course_id,
                )
            )
            .limit(1)
        )
        existing_reward = result.scalar_one_or_none()

        if existing_reward:
            logger.info(
                f"Reward already issued: user={user_id} course={course_id} reward={existing_reward.id}",
                extra={
                    "user_id": user_id,
                    "course_id": course_id,
                    "reward_id": existing_reward.id,
                },
            )
            return existing_reward

        # Issue reward via rewards service
        reward = await grant_discount(
            db=self.db,
            user_id=user_id,
            course_id=course_id,
            percent=course.reward_percent,
            expires_days=course.reward_expires_days or 30,
        )

        logger.info(
            f"Reward issued: {reward.id} user={user_id} course={course_id} discount={course.reward_percent}%",
            extra={
                "reward_id": reward.id,
                "user_id": user_id,
                "course_id": course_id,
                "discount_percent": course.reward_percent,
            },
        )

        return reward

    async def get_user_progress(self, user_id: str, course_id: str) -> dict[str, Any]:
        """Get user's progress in a course.

        Args:
            user_id: User UUID
            course_id: Course UUID

        Returns:
            Progress summary with attempts, completion status, and rewards
        """
        # Get course completion status
        completed, completion_details = await self.check_course_completion(
            user_id, course_id
        )

        # Get all attempts for this course
        result = await self.db.execute(
            select(Attempt)
            .where(
                and_(
                    Attempt.user_id == user_id,
                    Attempt.course_id == course_id,
                )
            )
            .order_by(Attempt.created_at.desc())
        )
        attempts = list(result.scalars().all())

        # Get rewards
        result = await self.db.execute(
            select(Reward).where(
                and_(
                    Reward.user_id == user_id,
                    Reward.course_id == course_id,
                )
            )
        )
        rewards = list(result.scalars().all())

        progress = {
            "course_id": course_id,
            "user_id": user_id,
            "completed": completed,
            "completion_details": completion_details,
            "total_attempts": len(attempts),
            "passed_attempts": sum(1 for a in attempts if a.passed),
            "latest_attempt": attempts[0] if attempts else None,
            "rewards": rewards,
        }

        return progress
