"""Comprehensive tests for PR-064 Education Content Pipeline & Quiz Engine.

Tests cover ALL business logic with REAL implementations:
- Course/Lesson/Quiz CRUD
- Quiz attempt submission and grading
- Rate limiting on retakes
- Max attempts enforcement
- Course completion tracking
- Reward issuance
- Error paths and edge cases

100% coverage target with production-ready validation.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.models import User, UserRole
from backend.app.education.models import (
    Attempt,
    Course,
    CourseStatus,
    Lesson,
    Quiz,
    QuizQuestion,
    Reward,
)
from backend.app.education.rewards import (
    get_active_rewards,
    grant_credit,
    grant_discount,
    redeem_reward,
)
from backend.app.education.service import EducationService


@pytest_asyncio.fixture
async def education_service(db: AsyncSession) -> EducationService:
    """Create education service with test database."""
    return EducationService(db)


@pytest_asyncio.fixture
async def sample_course(db: AsyncSession) -> Course:
    """Create a sample course for testing."""
    course = Course(
        id=str(uuid4()),
        title="Trading Fundamentals",
        description="Learn the basics of trading",
        status=CourseStatus.PUBLISHED,
        duration_minutes=60,
        difficulty_level=1,
        reward_percent=10.0,
        reward_expires_days=30,
        order_index=1,
    )
    db.add(course)
    await db.commit()
    await db.refresh(course)
    return course


@pytest_asyncio.fixture
async def sample_lesson(db: AsyncSession, sample_course: Course) -> Lesson:
    """Create a sample lesson for testing."""
    lesson = Lesson(
        id=str(uuid4()),
        course_id=sample_course.id,
        title="Introduction to Risk Management",
        content="# Risk Management\n\nThis lesson covers position sizing and stop losses.",
        order_index=1,
        duration_minutes=15,
        is_required=True,
    )
    db.add(lesson)
    await db.commit()
    await db.refresh(lesson)
    return lesson


@pytest_asyncio.fixture
async def sample_quiz(db: AsyncSession, sample_lesson: Lesson) -> Quiz:
    """Create a sample quiz for testing."""
    quiz = Quiz(
        id=str(uuid4()),
        lesson_id=sample_lesson.id,
        title="Risk Management Quiz",
        description="Test your knowledge of risk management",
        passing_score=70.0,
        max_attempts=3,
        retry_delay_minutes=5,
    )
    db.add(quiz)
    await db.commit()
    await db.refresh(quiz)
    return quiz


@pytest_asyncio.fixture
async def sample_questions(db: AsyncSession, sample_quiz: Quiz) -> list[QuizQuestion]:
    """Create sample quiz questions for testing."""
    questions = [
        QuizQuestion(
            id=str(uuid4()),
            quiz_id=sample_quiz.id,
            question_text="What is the recommended risk per trade?",
            options=["1-2% of account", "5-10% of account", "20% of account", "All in"],
            correct_answers=[0],  # First option is correct
            explanation="Risk 1-2% per trade to preserve capital.",
            order_index=1,
            points=1,
        ),
        QuizQuestion(
            id=str(uuid4()),
            quiz_id=sample_quiz.id,
            question_text="Which of these are important risk management tools? (Select all)",
            options=["Stop losses", "Position sizing", "Leverage", "Diversification"],
            correct_answers=[0, 1, 3],  # Stop losses, position sizing, diversification
            explanation="All are important except over-leveraging.",
            order_index=2,
            points=2,
        ),
        QuizQuestion(
            id=str(uuid4()),
            quiz_id=sample_quiz.id,
            question_text="What is a stop loss?",
            options=[
                "Exit price to limit losses",
                "Entry price for trades",
                "Profit target",
                "Trading fee",
            ],
            correct_answers=[0],
            explanation="Stop loss limits potential losses on a position.",
            order_index=3,
            points=1,
        ),
    ]

    for q in questions:
        db.add(q)

    await db.commit()

    for q in questions:
        await db.refresh(q)

    return questions


@pytest_asyncio.fixture
async def test_user(db: AsyncSession) -> User:
    """Create a test user."""
    user = User(
        id=str(uuid4()),
        email=f"test_edu_{uuid4()}@example.com",
        password_hash="hashed_secret",
        role=UserRole.USER,
        # is_active=True,  # These might not be in the model, checking...
        # is_verified=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


class TestCourseOperations:
    """Test course CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_course(self, db: AsyncSession):
        """Test course creation with all fields."""
        course = Course(
            id=str(uuid4()),
            title="Advanced Trading Strategies",
            description="Master complex trading techniques",
            status=CourseStatus.DRAFT,
            duration_minutes=120,
            difficulty_level=3,
            reward_percent=15.0,
            reward_expires_days=60,
            order_index=5,
            thumbnail_url="https://example.com/image.jpg",
        )

        db.add(course)
        await db.commit()
        await db.refresh(course)

        assert course.id is not None
        assert course.title == "Advanced Trading Strategies"
        assert course.status == CourseStatus.DRAFT
        assert course.difficulty_level == 3
        assert course.reward_percent == 15.0
        assert course.created_at is not None
        assert course.updated_at is not None

    @pytest.mark.asyncio
    async def test_list_published_courses(
        self, education_service: EducationService, sample_course: Course
    ):
        """Test listing only published courses (default)."""
        courses = await education_service.list_courses()

        assert len(courses) >= 1
        assert all(c.status == CourseStatus.PUBLISHED for c in courses)
        assert any(c.id == sample_course.id for c in courses)

    @pytest.mark.asyncio
    async def test_list_all_courses(
        self, education_service: EducationService, db: AsyncSession
    ):
        """Test listing courses with status filter."""
        # Create draft and published courses
        draft_course = Course(
            id=str(uuid4()),
            title="Draft Course",
            description="Not published yet",
            status=CourseStatus.DRAFT,
            duration_minutes=30,
            difficulty_level=1,
        )
        db.add(draft_course)
        await db.commit()

        # List draft courses
        draft_courses = await education_service.list_courses(status=CourseStatus.DRAFT)
        assert len(draft_courses) >= 1
        assert all(c.status == CourseStatus.DRAFT for c in draft_courses)

    @pytest.mark.asyncio
    async def test_get_course(
        self, education_service: EducationService, sample_course: Course
    ):
        """Test retrieving course by ID."""
        course = await education_service.get_course(sample_course.id)

        assert course is not None
        assert course.id == sample_course.id
        assert course.title == sample_course.title

    @pytest.mark.asyncio
    async def test_get_nonexistent_course(self, education_service: EducationService):
        """Test retrieving non-existent course returns None."""
        course = await education_service.get_course("nonexistent-id")
        assert course is None


class TestLessonOperations:
    """Test lesson operations."""

    @pytest.mark.asyncio
    async def test_create_lesson(self, db: AsyncSession, sample_course: Course):
        """Test lesson creation."""
        lesson = Lesson(
            id=str(uuid4()),
            course_id=sample_course.id,
            title="Technical Analysis Basics",
            content="# Technical Analysis\n\nSupport and resistance levels...",
            order_index=2,
            duration_minutes=20,
            is_required=False,
        )

        db.add(lesson)
        await db.commit()
        await db.refresh(lesson)

        assert lesson.id is not None
        assert lesson.course_id == sample_course.id
        assert lesson.is_required is False

    @pytest.mark.asyncio
    async def test_get_lesson(
        self, education_service: EducationService, sample_lesson: Lesson
    ):
        """Test retrieving lesson by ID."""
        lesson = await education_service.get_lesson(sample_lesson.id)

        assert lesson is not None
        assert lesson.id == sample_lesson.id
        assert lesson.title == sample_lesson.title


class TestQuizOperations:
    """Test quiz and question operations."""

    @pytest.mark.asyncio
    async def test_create_quiz(self, db: AsyncSession, sample_lesson: Lesson):
        """Test quiz creation."""
        quiz = Quiz(
            id=str(uuid4()),
            lesson_id=sample_lesson.id,
            title="Test Quiz",
            description="A test quiz",
            passing_score=80.0,
            max_attempts=None,  # Unlimited attempts
            retry_delay_minutes=0,  # No delay
        )

        db.add(quiz)
        await db.commit()
        await db.refresh(quiz)

        assert quiz.id is not None
        assert quiz.passing_score == 80.0
        assert quiz.max_attempts is None

    @pytest.mark.asyncio
    async def test_get_quiz(
        self, education_service: EducationService, sample_quiz: Quiz
    ):
        """Test retrieving quiz by ID."""
        quiz = await education_service.get_quiz(sample_quiz.id)

        assert quiz is not None
        assert quiz.id == sample_quiz.id
        assert quiz.passing_score == 70.0

    @pytest.mark.asyncio
    async def test_get_quiz_questions(
        self,
        education_service: EducationService,
        sample_quiz: Quiz,
        sample_questions: list[QuizQuestion],
    ):
        """Test retrieving quiz questions in order."""
        questions = await education_service.get_quiz_questions(sample_quiz.id)

        assert len(questions) == 3
        assert questions[0].order_index == 1
        assert questions[1].order_index == 2
        assert questions[2].order_index == 3
        assert all(q.quiz_id == sample_quiz.id for q in questions)


class TestQuizGrading:
    """Test quiz grading logic."""

    @pytest.mark.asyncio
    async def test_grade_perfect_score(
        self,
        education_service: EducationService,
        sample_quiz: Quiz,
        sample_questions: list[QuizQuestion],
    ):
        """Test grading with all correct answers."""
        answers = {
            sample_questions[0].id: [0],  # Correct: "1-2% of account"
            sample_questions[1].id: [
                0,
                1,
                3,
            ],  # Correct: stop losses, position sizing, diversification
            sample_questions[2].id: [0],  # Correct: "Exit price to limit losses"
        }

        score, passed, details = await education_service.grade_quiz(
            sample_quiz, sample_questions, answers
        )

        assert score == 100.0
        assert passed is True
        assert details["earned_points"] == 4  # 1 + 2 + 1 points
        assert details["total_points"] == 4
        assert all(q["correct"] for q in details["questions"])

    @pytest.mark.asyncio
    async def test_grade_partial_score(
        self,
        education_service: EducationService,
        sample_quiz: Quiz,
        sample_questions: list[QuizQuestion],
    ):
        """Test grading with some incorrect answers."""
        answers = {
            sample_questions[0].id: [0],  # Correct (1 point)
            sample_questions[1].id: [0, 1],  # Incorrect (0 points - missing answer)
            sample_questions[2].id: [1],  # Incorrect (0 points)
        }

        score, passed, details = await education_service.grade_quiz(
            sample_quiz, sample_questions, answers
        )

        assert score == 25.0  # 1 out of 4 points = 25%
        assert passed is False  # Below 70% passing score
        assert details["earned_points"] == 1
        assert details["total_points"] == 4

    @pytest.mark.asyncio
    async def test_grade_passing_score(
        self,
        education_service: EducationService,
        sample_quiz: Quiz,
        sample_questions: list[QuizQuestion],
    ):
        """Test grading at exactly passing threshold."""
        # Need 70% to pass = 2.8 out of 4 points
        # Get question 0 (1 pt) and question 1 (2 pts) correct = 3 pts = 75%
        answers = {
            sample_questions[0].id: [0],  # Correct (1 point)
            sample_questions[1].id: [0, 1, 3],  # Correct (2 points)
            sample_questions[2].id: [3],  # Incorrect (0 points)
        }

        score, passed, details = await education_service.grade_quiz(
            sample_quiz, sample_questions, answers
        )

        assert score == 75.0
        assert passed is True  # Above 70% passing score

    @pytest.mark.asyncio
    async def test_grade_empty_answers(
        self,
        education_service: EducationService,
        sample_quiz: Quiz,
        sample_questions: list[QuizQuestion],
    ):
        """Test grading with no answers provided."""
        answers = {}

        score, passed, details = await education_service.grade_quiz(
            sample_quiz, sample_questions, answers
        )

        assert score == 0.0
        assert passed is False
        assert details["earned_points"] == 0


class TestAttemptSubmission:
    """Test quiz attempt submission and validation."""

    @pytest.mark.asyncio
    async def test_submit_passing_attempt(
        self,
        education_service: EducationService,
        sample_course: Course,
        sample_quiz: Quiz,
        sample_questions: list[QuizQuestion],
    ):
        """Test submitting a passing quiz attempt."""
        user_id = str(uuid4())
        answers = {
            sample_questions[0].id: [0],
            sample_questions[1].id: [0, 1, 3],
            sample_questions[2].id: [0],
        }

        attempt, details = await education_service.submit_attempt(
            user_id=user_id,
            course_id=sample_course.id,
            quiz_id=sample_quiz.id,
            answers=answers,
            time_taken_seconds=120,
        )

        assert attempt.id is not None
        assert attempt.user_id == user_id
        assert attempt.score == 100.0
        assert attempt.passed is True
        assert attempt.time_taken_seconds == 120
        assert details["passed"] is True

    @pytest.mark.asyncio
    async def test_submit_failing_attempt(
        self,
        education_service: EducationService,
        sample_course: Course,
        sample_quiz: Quiz,
        sample_questions: list[QuizQuestion],
    ):
        """Test submitting a failing quiz attempt."""
        user_id = str(uuid4())
        answers = {
            sample_questions[0].id: [3],  # Wrong
            sample_questions[1].id: [2],  # Wrong
            sample_questions[2].id: [1],  # Wrong
        }

        attempt, details = await education_service.submit_attempt(
            user_id=user_id,
            course_id=sample_course.id,
            quiz_id=sample_quiz.id,
            answers=answers,
        )

        assert attempt.score == 0.0
        assert attempt.passed is False
        assert details["passed"] is False


class TestRateLimiting:
    """Test rate limiting on quiz retakes."""

    @pytest.mark.asyncio
    async def test_rate_limit_allows_first_attempt(
        self, education_service: EducationService, sample_quiz: Quiz
    ):
        """Test rate limit allows first attempt."""
        user_id = str(uuid4())

        can_attempt, available_at = await education_service.check_rate_limit(
            user_id, sample_quiz.id, sample_quiz.retry_delay_minutes
        )

        assert can_attempt is True
        assert available_at is None

    @pytest.mark.asyncio
    async def test_rate_limit_blocks_quick_retry(
        self,
        education_service: EducationService,
        db: AsyncSession,
        sample_course: Course,
        sample_quiz: Quiz,
        sample_questions: list[QuizQuestion],
    ):
        """Test rate limit blocks immediate retries."""
        user_id = str(uuid4())

        # Submit first attempt
        await education_service.submit_attempt(
            user_id=user_id,
            course_id=sample_course.id,
            quiz_id=sample_quiz.id,
            answers={sample_questions[0].id: [0]},
        )

        # Try to submit immediately (within 5 min delay)
        can_attempt, available_at = await education_service.check_rate_limit(
            user_id, sample_quiz.id, sample_quiz.retry_delay_minutes
        )

        assert can_attempt is False
        assert available_at is not None
        assert available_at > datetime.now(UTC)

    @pytest.mark.asyncio
    async def test_rate_limit_allows_after_delay(
        self,
        education_service: EducationService,
        db: AsyncSession,
        sample_course: Course,
        sample_quiz: Quiz,
        sample_questions: list[QuizQuestion],
    ):
        """Test rate limit allows retry after delay period."""
        user_id = str(uuid4())

        # Create an old attempt (10 minutes ago)
        old_attempt = Attempt(
            id=str(uuid4()),
            user_id=user_id,
            course_id=sample_course.id,
            quiz_id=sample_quiz.id,
            answers={},
            score=0.0,
            passed=False,
            created_at=datetime.now(UTC) - timedelta(minutes=10),
        )
        db.add(old_attempt)
        await db.commit()

        # Check rate limit (5 min delay, 10 min passed)
        can_attempt, available_at = await education_service.check_rate_limit(
            user_id, sample_quiz.id, sample_quiz.retry_delay_minutes
        )

        assert can_attempt is True
        assert available_at is None

    @pytest.mark.asyncio
    async def test_no_rate_limit_when_disabled(
        self,
        education_service: EducationService,
        db: AsyncSession,
        sample_lesson: Lesson,
    ):
        """Test no rate limiting when retry_delay_minutes = 0."""
        user_id = str(uuid4())

        # Create quiz with no delay
        quiz = Quiz(
            id=str(uuid4()),
            lesson_id=sample_lesson.id,
            title="Unlimited Retries Quiz",
            passing_score=70.0,
            retry_delay_minutes=0,  # No delay
        )
        db.add(quiz)
        await db.commit()

        # Check rate limit
        can_attempt, available_at = await education_service.check_rate_limit(
            user_id, quiz.id, quiz.retry_delay_minutes
        )

        assert can_attempt is True
        assert available_at is None


class TestMaxAttempts:
    """Test maximum attempts enforcement."""

    @pytest.mark.asyncio
    async def test_max_attempts_unlimited(
        self, education_service: EducationService, sample_quiz: Quiz
    ):
        """Test unlimited attempts when max_attempts is None."""
        user_id = str(uuid4())

        # Create quiz with unlimited attempts
        sample_quiz.max_attempts = None

        can_attempt, attempts_used = await education_service.check_max_attempts(
            user_id, sample_quiz.id, None
        )

        assert can_attempt is True
        assert attempts_used == 0

    @pytest.mark.asyncio
    async def test_max_attempts_not_reached(
        self,
        education_service: EducationService,
        db: AsyncSession,
        sample_course: Course,
        sample_quiz: Quiz,
    ):
        """Test max attempts not reached."""
        user_id = str(uuid4())

        # Create 1 attempt (max is 3)
        attempt = Attempt(
            id=str(uuid4()),
            user_id=user_id,
            course_id=sample_course.id,
            quiz_id=sample_quiz.id,
            answers={},
            score=50.0,
            passed=False,
        )
        db.add(attempt)
        await db.commit()

        can_attempt, attempts_used = await education_service.check_max_attempts(
            user_id, sample_quiz.id, sample_quiz.max_attempts
        )

        assert can_attempt is True
        assert attempts_used == 1

    @pytest.mark.asyncio
    async def test_max_attempts_reached(
        self,
        education_service: EducationService,
        db: AsyncSession,
        sample_course: Course,
        sample_quiz: Quiz,
    ):
        """Test max attempts reached blocks further attempts."""
        user_id = str(uuid4())

        # Create 3 attempts (max is 3)
        for _ in range(3):
            attempt = Attempt(
                id=str(uuid4()),
                user_id=user_id,
                course_id=sample_course.id,
                quiz_id=sample_quiz.id,
                answers={},
                score=50.0,
                passed=False,
            )
            db.add(attempt)
        await db.commit()

        can_attempt, attempts_used = await education_service.check_max_attempts(
            user_id, sample_quiz.id, sample_quiz.max_attempts
        )

        assert can_attempt is False
        assert attempts_used == 3

    @pytest.mark.asyncio
    async def test_submit_exceeds_max_attempts(
        self,
        education_service: EducationService,
        db: AsyncSession,
        sample_course: Course,
        sample_quiz: Quiz,
        sample_questions: list[QuizQuestion],
    ):
        """Test submitting attempt when max attempts exceeded raises error."""
        user_id = str(uuid4())

        # Create 3 attempts (max is 3)
        for i in range(3):
            attempt = Attempt(
                id=str(uuid4()),
                user_id=user_id,
                course_id=sample_course.id,
                quiz_id=sample_quiz.id,
                answers={},
                score=50.0,
                passed=False,
                created_at=datetime.now(UTC) - timedelta(minutes=30 * (i + 1)),
            )
            db.add(attempt)
        await db.commit()

        # Try to submit 4th attempt
        with pytest.raises(ValueError, match="Maximum attempts reached"):
            await education_service.submit_attempt(
                user_id=user_id,
                course_id=sample_course.id,
                quiz_id=sample_quiz.id,
                answers={sample_questions[0].id: [0]},
            )


class TestCourseCompletion:
    """Test course completion tracking."""

    @pytest.mark.asyncio
    async def test_course_completion_no_lessons(
        self, education_service: EducationService, db: AsyncSession
    ):
        """Test course with no required lessons is considered complete."""
        user_id = str(uuid4())

        # Create course with no lessons (still needs valid duration)
        course = Course(
            id=str(uuid4()),
            title="Empty Course",
            description="No lessons",
            status=CourseStatus.PUBLISHED,
            duration_minutes=1,  # Minimum valid duration
            difficulty_level=1,
        )
        db.add(course)
        await db.commit()

        completed, details = await education_service.check_course_completion(
            user_id, course.id
        )

        assert completed is True
        assert details["completion_rate"] == 100.0

    @pytest.mark.asyncio
    async def test_course_completion_all_passed(
        self,
        education_service: EducationService,
        db: AsyncSession,
        sample_course: Course,
        sample_lesson: Lesson,
        sample_quiz: Quiz,
        sample_questions: list[QuizQuestion],
    ):
        """Test course completion when all required lessons passed."""
        user_id = str(uuid4())

        # Create passing attempt
        attempt = Attempt(
            id=str(uuid4()),
            user_id=user_id,
            course_id=sample_course.id,
            quiz_id=sample_quiz.id,
            answers={},
            score=100.0,
            passed=True,
        )
        db.add(attempt)
        await db.commit()

        completed, details = await education_service.check_course_completion(
            user_id, sample_course.id
        )

        assert completed is True
        assert details["completion_rate"] == 100.0
        assert details["required_lessons"] == 1
        assert details["completed_lessons"] == 1

    @pytest.mark.asyncio
    async def test_course_completion_partial(
        self,
        education_service: EducationService,
        db: AsyncSession,
        sample_course: Course,
        sample_lesson: Lesson,
        sample_quiz: Quiz,
    ):
        """Test partial course completion."""
        user_id = str(uuid4())

        # Create another required lesson without passing
        lesson2 = Lesson(
            id=str(uuid4()),
            course_id=sample_course.id,
            title="Advanced Topics",
            content="Advanced content",
            order_index=2,
            duration_minutes=20,
            is_required=True,
        )
        db.add(lesson2)

        quiz2 = Quiz(
            id=str(uuid4()),
            lesson_id=lesson2.id,
            title="Advanced Quiz",
            passing_score=70.0,
        )
        db.add(quiz2)
        await db.commit()

        # Pass only first lesson - use sample_quiz fixture directly
        quiz1 = sample_quiz

        attempt1 = Attempt(
            id=str(uuid4()),
            user_id=user_id,
            course_id=sample_course.id,
            quiz_id=quiz1.id,
            answers={},
            score=100.0,
            passed=True,
        )
        db.add(attempt1)
        await db.commit()

        completed, details = await education_service.check_course_completion(
            user_id, sample_course.id
        )

        assert completed is False
        assert details["completion_rate"] == 50.0
        assert details["required_lessons"] == 2
        assert details["completed_lessons"] == 1


class TestRewardIssuance:
    """Test reward creation and management."""

    @pytest.mark.asyncio
    async def test_grant_discount(
        self, db: AsyncSession, test_user: User, sample_course: Course
    ):
        """Test granting a discount reward."""
        user_id = test_user.id
        course_id = sample_course.id

        reward = await grant_discount(
            db=db,
            user_id=user_id,
            course_id=course_id,
            percent=15.0,
            expires_days=45,
        )

        assert reward.id is not None
        assert reward.user_id == user_id
        assert reward.course_id == course_id
        assert reward.reward_type == "discount"
        assert reward.reward_value == 15.0
        assert reward.currency is None
        assert reward.redeemed_at is None

        # Handle SQLite naive datetime: convert to aware if needed
        expires_at = reward.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        assert expires_at > datetime.now(UTC)

    @pytest.mark.asyncio
    async def test_grant_discount_invalid_percent(
        self, db: AsyncSession, test_user: User, sample_course: Course
    ):
        """Test granting discount with invalid percent raises error."""
        with pytest.raises(ValueError, match="Invalid discount percent"):
            await grant_discount(
                db=db,
                user_id=test_user.id,
                course_id=sample_course.id,
                percent=150.0,  # Invalid: > 100%
                expires_days=30,
            )

    @pytest.mark.asyncio
    async def test_grant_credit(
        self, db: AsyncSession, test_user: User, sample_course: Course
    ):
        """Test granting a credit reward."""
        user_id = test_user.id
        course_id = sample_course.id

        reward = await grant_credit(
            db=db,
            user_id=user_id,
            course_id=course_id,
            amount=10.0,
            currency="GBP",
            expires_days=60,
        )

        assert reward.id is not None
        assert reward.reward_type == "credit"
        assert reward.reward_value == 10.0
        assert reward.currency == "GBP"

    @pytest.mark.asyncio
    async def test_grant_credit_invalid_amount(
        self, db: AsyncSession, test_user: User, sample_course: Course
    ):
        """Test granting credit with invalid amount raises error."""
        with pytest.raises(ValueError, match="Invalid credit amount"):
            await grant_credit(
                db=db,
                user_id=test_user.id,
                course_id=sample_course.id,
                amount=-5.0,  # Invalid: negative
                currency="GBP",
                expires_days=30,
            )

    @pytest.mark.asyncio
    async def test_redeem_reward(
        self, db: AsyncSession, test_user: User, sample_course: Course
    ):
        """Test redeeming a reward."""
        user_id = test_user.id
        course_id = sample_course.id

        # Create reward
        reward = await grant_discount(
            db=db,
            user_id=user_id,
            course_id=course_id,
            percent=10.0,
            expires_days=30,
        )

        # Redeem reward
        order_id = "order-123"
        redeemed = await redeem_reward(db, reward.id, order_id)

        assert redeemed.redeemed_at is not None
        # Verify redeemed_at is recent (within last minute)
        now = datetime.now(UTC)
        redeemed_at = redeemed.redeemed_at
        if redeemed_at.tzinfo is None:
            redeemed_at = redeemed_at.replace(tzinfo=UTC)
        time_diff = now - redeemed_at
        assert time_diff.total_seconds() < 60  # Within last 60 seconds
        assert redeemed.redemption_order_id == order_id

    @pytest.mark.asyncio
    async def test_redeem_already_redeemed(
        self, db: AsyncSession, test_user: User, sample_course: Course
    ):
        """Test redeeming already redeemed reward raises error."""
        user_id = test_user.id
        course_id = sample_course.id

        # Create and redeem reward
        reward = await grant_discount(
            db=db,
            user_id=user_id,
            course_id=course_id,
            percent=10.0,
            expires_days=30,
        )
        await redeem_reward(db, reward.id, "order-1")

        # Try to redeem again
        with pytest.raises(ValueError, match="already redeemed"):
            await redeem_reward(db, reward.id, "order-2")

    @pytest.mark.asyncio
    async def test_redeem_expired_reward(
        self, db: AsyncSession, test_user: User, sample_course: Course
    ):
        """Test redeeming expired reward raises error."""
        user_id = test_user.id
        course_id = sample_course.id

        # Create expired reward
        reward = Reward(
            id=str(uuid4()),
            user_id=user_id,
            course_id=course_id,
            reward_type="discount",
            reward_value=10.0,
            issued_at=datetime.now(UTC) - timedelta(days=60),
            expires_at=datetime.now(UTC) - timedelta(days=1),  # Expired yesterday
        )
        db.add(reward)
        await db.commit()
        await db.refresh(reward)

        # Try to redeem
        with pytest.raises(ValueError, match="expired"):
            await redeem_reward(db, reward.id, "order-1")

    @pytest.mark.asyncio
    async def test_get_active_rewards(
        self, db: AsyncSession, test_user: User, sample_course: Course
    ):
        """Test retrieving active rewards."""
        user_id = test_user.id
        course1_id = sample_course.id

        # Create a second course for variety
        course2 = Course(
            id=str(uuid4()),
            title="Course 2",
            description="Desc",
            difficulty_level=1,
            duration_minutes=60,
            status=CourseStatus.PUBLISHED,
        )
        db.add(course2)
        await db.commit()
        course2_id = course2.id

        # Create active discount
        await grant_discount(
            db=db,
            user_id=user_id,
            course_id=course1_id,
            percent=10.0,
            expires_days=30,
        )

        # Create active credit
        await grant_credit(
            db=db,
            user_id=user_id,
            course_id=course2_id,
            amount=5.0,
            currency="GBP",
            expires_days=30,
        )

        # Create expired reward
        expired_reward = Reward(
            id=str(uuid4()),
            user_id=user_id,
            course_id=course1_id,
            reward_type="discount",
            reward_value=20.0,
            issued_at=datetime.now(UTC) - timedelta(days=60),
            expires_at=datetime.now(UTC) - timedelta(days=1),
        )
        db.add(expired_reward)
        await db.commit()

        # Get all active rewards
        active = await get_active_rewards(db, user_id)

        assert len(active) == 2
        assert all(r.redeemed_at is None for r in active)
        # Handle SQLite naive datetimes
        now = datetime.now(UTC)
        for r in active:
            expires_at = r.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            assert expires_at > now

    @pytest.mark.asyncio
    async def test_get_active_rewards_by_type(
        self, db: AsyncSession, test_user: User, sample_course: Course
    ):
        """Test filtering active rewards by type."""
        user_id = test_user.id
        course_id = sample_course.id

        # Create mixed rewards
        await grant_discount(
            db=db,
            user_id=user_id,
            course_id=course_id,
            percent=10.0,
            expires_days=30,
        )
        await grant_credit(
            db=db,
            user_id=user_id,
            course_id=course_id,
            amount=5.0,
            currency="GBP",
            expires_days=30,
        )

        # Get only discounts
        discounts = await get_active_rewards(db, user_id, reward_type="discount")
        assert len(discounts) == 1
        assert all(r.reward_type == "discount" for r in discounts)

        # Get only credits
        credits = await get_active_rewards(db, user_id, reward_type="credit")
        assert len(credits) == 1
        assert all(r.reward_type == "credit" for r in credits)


class TestRewardAutoIssuance:
    """Test automatic reward issuance on course completion."""

    @pytest.mark.asyncio
    async def test_issue_reward_on_completion(
        self,
        education_service: EducationService,
        db: AsyncSession,
        sample_course: Course,
        sample_lesson: Lesson,
        sample_quiz: Quiz,
    ):
        """Test reward issued when course completed."""
        user_id = str(uuid4())

        # Pass quiz
        attempt = Attempt(
            id=str(uuid4()),
            user_id=user_id,
            course_id=sample_course.id,
            quiz_id=sample_quiz.id,
            answers={},
            score=100.0,
            passed=True,
        )
        db.add(attempt)
        await db.commit()

        # Issue reward
        reward = await education_service.issue_course_reward(user_id, sample_course.id)

        assert reward is not None
        assert reward.user_id == user_id
        assert reward.course_id == sample_course.id
        assert reward.reward_value == sample_course.reward_percent

    @pytest.mark.asyncio
    async def test_no_duplicate_rewards(
        self,
        education_service: EducationService,
        db: AsyncSession,
        sample_course: Course,
        sample_lesson: Lesson,
        sample_quiz: Quiz,
    ):
        """Test reward not issued twice for same course."""
        user_id = str(uuid4())

        # Pass quiz
        attempt = Attempt(
            id=str(uuid4()),
            user_id=user_id,
            course_id=sample_course.id,
            quiz_id=sample_quiz.id,
            answers={},
            score=100.0,
            passed=True,
        )
        db.add(attempt)
        await db.commit()

        # Issue first reward
        reward1 = await education_service.issue_course_reward(user_id, sample_course.id)
        assert reward1 is not None

        # Try to issue second reward
        reward2 = await education_service.issue_course_reward(user_id, sample_course.id)

        # Should return existing reward, not create new one
        assert reward2.id == reward1.id

    @pytest.mark.asyncio
    async def test_no_reward_when_not_completed(
        self,
        db: AsyncSession,
        education_service: EducationService,
    ):
        """Test reward not issued when course not completed."""
        user_id = str(uuid4())

        # Create course with required lesson (so it's NOT auto-complete)
        course = Course(
            id=str(uuid4()),
            title="Advanced Trading",
            description="Advanced trading strategies",
            status=CourseStatus.PUBLISHED,
            duration_minutes=120,
            difficulty_level=2,
            reward_percent=15.0,
            reward_expires_days=30,
            order_index=2,
        )
        db.add(course)

        # Create required lesson (no quiz = would be complete, so add quiz)
        lesson = Lesson(
            id=str(uuid4()),
            course_id=course.id,
            title="Advanced Strategies",
            content="Learn advanced trading",
            order_index=1,
            duration_minutes=60,
            is_required=True,
        )
        db.add(lesson)

        # Create quiz for lesson (required lesson + quiz = must pass to complete)
        quiz = Quiz(
            id=str(uuid4()),
            lesson_id=lesson.id,
            title="Strategy Quiz",
            description="Test your knowledge",
            passing_score=70.0,
            max_attempts=3,
            retry_delay_minutes=0,
        )
        db.add(quiz)
        await db.commit()

        # Try to issue reward without passing quiz (course not complete)
        with pytest.raises(ValueError, match="not completed"):
            await education_service.issue_course_reward(user_id, course.id)

    @pytest.mark.asyncio
    async def test_no_reward_when_not_configured(
        self,
        education_service: EducationService,
        db: AsyncSession,
        sample_lesson: Lesson,
    ):
        """Test no reward issued when course has no reward configured."""
        user_id = str(uuid4())

        # Create course without reward
        course = Course(
            id=str(uuid4()),
            title="No Reward Course",
            description="No reward",
            status=CourseStatus.PUBLISHED,
            duration_minutes=30,
            difficulty_level=1,
            reward_percent=None,  # No reward
        )
        db.add(course)

        # Create lesson and quiz
        lesson = Lesson(
            id=str(uuid4()),
            course_id=course.id,
            title="Lesson",
            content="Content",
            order_index=1,
            duration_minutes=10,
            is_required=True,
        )
        db.add(lesson)

        quiz = Quiz(
            id=str(uuid4()),
            lesson_id=lesson.id,
            title="Quiz",
            passing_score=70.0,
        )
        db.add(quiz)
        await db.commit()

        # Pass quiz
        attempt = Attempt(
            id=str(uuid4()),
            user_id=user_id,
            course_id=course.id,
            quiz_id=quiz.id,
            answers={},
            score=100.0,
            passed=True,
        )
        db.add(attempt)
        await db.commit()

        # Try to issue reward
        reward = await education_service.issue_course_reward(user_id, course.id)

        assert reward is None


class TestUserProgress:
    """Test user progress tracking."""

    @pytest.mark.asyncio
    async def test_get_user_progress(
        self,
        education_service: EducationService,
        db: AsyncSession,
        sample_course: Course,
        sample_lesson: Lesson,
        sample_quiz: Quiz,
    ):
        """Test retrieving user progress in a course."""
        user_id = str(uuid4())

        # Create multiple attempts
        for i in range(3):
            attempt = Attempt(
                id=str(uuid4()),
                user_id=user_id,
                course_id=sample_course.id,
                quiz_id=sample_quiz.id,
                answers={},
                score=50.0 + i * 10,
                passed=i == 2,  # Last attempt passes
                created_at=datetime.now(UTC) - timedelta(hours=3 - i),
            )
            db.add(attempt)
        await db.commit()

        # Get progress
        progress = await education_service.get_user_progress(user_id, sample_course.id)

        assert progress["course_id"] == sample_course.id
        assert progress["user_id"] == user_id
        assert progress["total_attempts"] == 3
        assert progress["passed_attempts"] == 1
        assert progress["completed"] is True
        assert progress["latest_attempt"].score == 70.0

    @pytest.mark.asyncio
    async def test_get_progress_no_attempts(
        self,
        education_service: EducationService,
        sample_course: Course,
    ):
        """Test progress with no attempts."""
        user_id = str(uuid4())

        progress = await education_service.get_user_progress(user_id, sample_course.id)

        assert progress["total_attempts"] == 0
        assert progress["passed_attempts"] == 0
        assert progress["latest_attempt"] is None
        assert len(progress["rewards"]) == 0
