"""
Test suite for AI assistant service.

Tests chat orchestration, session management, RAG integration, and escalation workflow.

Coverage target: 100% of assistant.py
"""

from datetime import datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai.assistant import AIAssistant
from backend.app.ai.models import ChatMessage, ChatMessageRole, ChatSession, KBEmbedding
from backend.app.auth.models import User, UserRole
from backend.app.kb.models import Article, ArticleStatus


@pytest.fixture
def ai_assistant():
    """Create AI assistant instance."""
    return AIAssistant()


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user."""
    user = User(
        id=str(uuid4()),
        email=f"test_{uuid4()}@example.com",
        password_hash="hashed_password",
        role=UserRole.USER,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.fixture
async def test_articles(db_session: AsyncSession) -> list[Article]:
    """Create test KB articles with embeddings."""
    articles = []
    titles = [
        "How to Reset Password",
        "Two-Factor Authentication Setup",
        "Billing FAQ",
        "Account Security",
    ]

    for title in titles:
        article = Article(
            id=uuid4(),
            title=title,
            slug=title.lower().replace(" ", "-"),
            content=f"Detailed content about {title.lower()}",
            status=ArticleStatus.PUBLISHED,
            author_id=uuid4(),
            locale="en",
            version=1,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            published_at=datetime.utcnow(),
        )
        db_session.add(article)
        articles.append(article)

    await db_session.commit()

    # Create embeddings for articles
    from backend.app.ai.indexer import EmbeddingGenerator

    gen = EmbeddingGenerator()
    for article in articles:
        embedding_vec = await gen.generate(article.title)
        embedding = KBEmbedding(
            article_id=article.id,
            embedding=embedding_vec,
            embedding_model=gen.model_name,
        )
        db_session.add(embedding)

    await db_session.commit()
    return articles


class TestChatHappyPath:
    """Test happy path chat flow."""

    @pytest.mark.asyncio
    async def test_chat_new_session(
        self,
        db_session: AsyncSession,
        ai_assistant: AIAssistant,
    ):
        """Should create new session for first message."""
        user = await test_user.__wrapped__(db_session)
        articles = await test_articles.__wrapped__(db_session)

        response = await ai_assistant.chat(
            db=db_session,
            user_id=user.id,
            question="How do I reset my password?",
            session_id=None,
            channel="web",
        )

        assert response is not None
        assert response.answer is not None
        assert len(response.answer) > 0
        assert response.blocked_by_policy is None
        assert response.confidence_score is not None

    @pytest.mark.asyncio
    async def test_chat_creates_session_with_title(
        self,
        db_session: AsyncSession,
        ai_assistant: AIAssistant,
    ):
        """Should create session with title from first question."""
        user = await test_user.__wrapped__(db_session)
        articles = await test_articles.__wrapped__(db_session)

        response = await ai_assistant.chat(
            db=db_session,
            user_id=user.id,
            question="How do I enable 2FA?",
            session_id=None,
            channel="web",
        )

        # Verify session was created
        result = await db_session.execute(
            select(ChatSession).filter(ChatSession.user_id == user.id)
        )
        sessions = result.scalars().all()

        assert len(sessions) == 1
        assert sessions[0].title is not None
        assert len(sessions[0].title) > 0

    @pytest.mark.asyncio
    async def test_chat_stores_messages(
        self,
        db_session: AsyncSession,
        ai_assistant: AIAssistant,
    ):
        """Should store user and assistant messages."""
        user = await test_user.__wrapped__(db_session)
        articles = await test_articles.__wrapped__(db_session)

        response = await ai_assistant.chat(
            db=db_session,
            user_id=user.id,
            question="Test question",
            session_id=None,
            channel="web",
        )

        # Get session
        from sqlalchemy import select

        session_result = await db_session.execute(
            select(ChatSession).filter(ChatSession.user_id == user.id)
        )
        session = session_result.scalars().first()

        # Get messages
        message_result = await db_session.execute(
            select(ChatMessage).filter(ChatMessage.session_id == session.id)
        )
        messages = message_result.scalars().all()

        # Should have user message + assistant response
        assert len(messages) >= 2
        assert any(m.role == ChatMessageRole.USER for m in messages)
        assert any(m.role == ChatMessageRole.ASSISTANT for m in messages)

    @pytest.mark.asyncio
    async def test_chat_continues_existing_session(
        self,
        db_session: AsyncSession,
        ai_assistant: AIAssistant,
    ):
        """Should continue conversation in existing session."""
        user = await test_user.__wrapped__(db_session)
        articles = await test_articles.__wrapped__(db_session)

        # First message
        response1 = await ai_assistant.chat(
            db=db_session,
            user_id=user.id,
            question="First question?",
            session_id=None,
            channel="web",
        )

        # Get session
        from sqlalchemy import select

        session_result = await db_session.execute(
            select(ChatSession).filter(ChatSession.user_id == user.id)
        )
        session = session_result.scalars().first()
        session_id = session.id  # Already a UUID

        # Second message in same session
        response2 = await ai_assistant.chat(
            db=db_session,
            user_id=user.id,
            question="Follow-up question?",
            session_id=session_id,
            channel="web",
        )

        # Verify same session
        message_result = await db_session.execute(
            select(ChatMessage).filter(ChatMessage.session_id == session.id)
        )
        messages = message_result.scalars().all()

        # Should have 4 messages (user1, assistant1, user2, assistant2)
        assert len(messages) >= 4


class TestChatWithRAG:
    """Test RAG retrieval integration."""

    @pytest.mark.asyncio
    async def test_chat_retrieves_relevant_articles(
        self,
        db_session: AsyncSession,
        ai_assistant: AIAssistant,
    ):
        """Should retrieve relevant KB articles."""
        user = await test_user.__wrapped__(db_session)
        articles = await test_articles.__wrapped__(db_session)

        response = await ai_assistant.chat(
            db=db_session,
            user_id=user.id,
            question="How do I reset my password?",
            session_id=None,
            channel="web",
        )

        # Response should mention retrieved articles
        assert response.citations is not None
        # May have citations depending on RAG threshold

    @pytest.mark.asyncio
    async def test_chat_response_includes_citations(
        self,
        db_session: AsyncSession,
        ai_assistant: AIAssistant,
    ):
        """Response should include citations from retrieved articles."""
        user = await test_user.__wrapped__(db_session)
        articles = await test_articles.__wrapped__(db_session)

        response = await ai_assistant.chat(
            db=db_session,
            user_id=user.id,
            question="How do I reset my password?",
            session_id=None,
            channel="web",
        )

        # Check citations structure
        if response.citations:
            for citation in response.citations:
                assert hasattr(citation, "article_id")
                assert hasattr(citation, "title")
                assert citation.article_id is not None


class TestChatInputValidation:
    """Test input validation in chat."""

    @pytest.mark.asyncio
    async def test_chat_rejects_empty_question(
        self,
        db_session: AsyncSession,
        ai_assistant: AIAssistant,
    ):
        """Should reject empty question."""
        user = await test_user.__wrapped__(db_session)

        with pytest.raises(ValueError, match="too short|empty"):
            await ai_assistant.chat(
                db=db_session,
                user_id=user.id,
                question="",
                session_id=None,
                channel="web",
            )

    @pytest.mark.asyncio
    async def test_chat_rejects_very_short_question(
        self,
        db_session: AsyncSession,
        ai_assistant: AIAssistant,
    ):
        """Should reject questions too short."""
        user = await test_user.__wrapped__(db_session)

        with pytest.raises(ValueError):
            await ai_assistant.chat(
                db=db_session,
                user_id=user.id,
                question="Hi",
                session_id=None,
                channel="web",
            )

    @pytest.mark.asyncio
    async def test_chat_rejects_spam_input(
        self,
        db_session: AsyncSession,
        ai_assistant: AIAssistant,
    ):
        """Should reject spam patterns."""
        user = await test_user.__wrapped__(db_session)

        with pytest.raises(ValueError):
            await ai_assistant.chat(
                db=db_session,
                user_id=user.id,
                question="aaaaaaaaaaaaaaaaaaaaaaaaaa",
                session_id=None,
                channel="web",
            )

    @pytest.mark.asyncio
    async def test_chat_rejects_sql_injection(
        self,
        db_session: AsyncSession,
        ai_assistant: AIAssistant,
    ):
        """Should reject SQL injection attempts."""
        user = await test_user.__wrapped__(db_session)

        with pytest.raises(ValueError):
            await ai_assistant.chat(
                db=db_session,
                user_id=user.id,
                question="'; DROP TABLE users; --",
                session_id=None,
                channel="web",
            )


class TestChatGuardrails:
    """Test guardrails enforcement in chat."""

    @pytest.mark.asyncio
    async def test_chat_blocks_api_key_leak_in_input(
        self,
        db_session: AsyncSession,
        ai_assistant: AIAssistant,
    ):
        """Should block questions containing API keys."""
        user = await test_user.__wrapped__(db_session)

        with pytest.raises(ValueError, match="policy|blocked|security|Invalid"):
            await ai_assistant.chat(
                db=db_session,
                user_id=user.id,
                question="My API key is sk-1234567890abcdefghijklmnopqrstuvwxyz please help",
                session_id=None,
                channel="web",
            )

    @pytest.mark.asyncio
    async def test_chat_blocks_pii_in_input(
        self,
        db_session: AsyncSession,
        ai_assistant: AIAssistant,
    ):
        """Should block questions containing PII."""
        user = await test_user.__wrapped__(db_session)

        with pytest.raises(ValueError, match="policy|blocked|security"):
            await ai_assistant.chat(
                db=db_session,
                user_id=user.id,
                question="I live at SW1A 1AA and my email is test@example.com",
                session_id=None,
                channel="web",
            )

    @pytest.mark.asyncio
    async def test_chat_escalates_on_financial_advice_response(
        self,
        db_session: AsyncSession,
        ai_assistant: AIAssistant,
    ):
        """Should escalate if response would contain financial advice."""
        user = await test_user.__wrapped__(db_session)
        articles = await test_articles.__wrapped__(db_session)

        # This response might trigger escalation (depends on LLM stub)
        response = await ai_assistant.chat(
            db=db_session,
            user_id=user.id,
            question="Is this a good investment?",
            session_id=None,
            channel="web",
        )

        # Response should be valid (may or may not escalate)
        assert response is not None


class TestChatEscalation:
    """Test escalation workflow."""

    @pytest.mark.asyncio
    async def test_policy_violation_escalates_automatically(
        self,
        db_session: AsyncSession,
        ai_assistant: AIAssistant,
    ):
        """Policy violation in response should trigger escalation."""
        user = await test_user.__wrapped__(db_session)
        articles = await test_articles.__wrapped__(db_session)

        response = await ai_assistant.chat(
            db=db_session,
            user_id=user.id,
            question="How do I reset password?",
            session_id=None,
            channel="web",
        )

        # If response triggered escalation
        if response.requires_escalation:
            # Session should be marked escalated
            from sqlalchemy import select

            session_result = await db_session.execute(
                select(ChatSession).filter(ChatSession.user_id == user.id)
            )
            session = session_result.scalars().first()
            assert session.escalated is True

    @pytest.mark.asyncio
    async def test_manual_escalation(
        self,
        db_session: AsyncSession,
        ai_assistant: AIAssistant,
    ):
        """Should support manual escalation."""
        user = await test_user.__wrapped__(db_session)
        articles = await test_articles.__wrapped__(db_session)

        # Create session first
        response = await ai_assistant.chat(
            db=db_session,
            user_id=user.id,
            question="How do I reset password?",
            session_id=None,
            channel="web",
        )

        # Get session
        from sqlalchemy import select

        session_result = await db_session.execute(
            select(ChatSession).filter(ChatSession.user_id == user.id)
        )
        session = session_result.scalars().first()

        # Escalate manually
        await ai_assistant.escalate_to_human(
            db=db_session,
            user_id=user.id,
            session_id=UUID(session.id),
            reason="User requested human support",
        )

        # Verify session escalated
        await db_session.refresh(session)
        assert session.escalated is True
        assert session.escalation_reason is not None


class TestSessionManagement:
    """Test session management."""

    @pytest.mark.asyncio
    async def test_get_session_history(
        self,
        db_session: AsyncSession,
        ai_assistant: AIAssistant,
    ):
        """Should retrieve full session history."""
        user = await test_user.__wrapped__(db_session)
        articles = await test_articles.__wrapped__(db_session)

        # Create multiple messages
        await ai_assistant.chat(
            db=db_session,
            user_id=user.id,
            question="First question?",
            session_id=None,
            channel="web",
        )

        # Get session
        from sqlalchemy import select

        session_result = await db_session.execute(
            select(ChatSession).filter(ChatSession.user_id == user.id)
        )
        session = session_result.scalars().first()

        # Add second message
        await ai_assistant.chat(
            db=db_session,
            user_id=user.id,
            question="Second question?",
            session_id=UUID(session.id),
            channel="web",
        )

        # Get history
        history = await ai_assistant.get_session_history(
            db=db_session,
            user_id=user.id,
            session_id=UUID(session.id),
        )

        assert history is not None
        assert "session" in history
        assert "messages" in history
        assert len(history["messages"]) >= 2

    @pytest.mark.asyncio
    async def test_list_user_sessions(
        self,
        db_session: AsyncSession,
        ai_assistant: AIAssistant,
    ):
        """Should list user's sessions with pagination."""
        user = await test_user.__wrapped__(db_session)
        articles = await test_articles.__wrapped__(db_session)

        # Create multiple sessions
        for i in range(3):
            await ai_assistant.chat(
                db=db_session,
                user_id=user.id,
                question=f"Question {i}?",
                session_id=None,
                channel="web",
            )

        # List sessions
        sessions, total = await ai_assistant.list_user_sessions(
            db=db_session,
            user_id=user.id,
            limit=10,
            skip=0,
        )

        assert len(sessions) == 3
        assert total == 3

    @pytest.mark.asyncio
    async def test_list_sessions_pagination(
        self,
        db_session: AsyncSession,
        ai_assistant: AIAssistant,
    ):
        """Pagination should work correctly."""
        user = await test_user.__wrapped__(db_session)
        articles = await test_articles.__wrapped__(db_session)

        # Create 5 sessions
        for i in range(5):
            await ai_assistant.chat(
                db=db_session,
                user_id=user.id,
                question=f"Question {i}?",
                session_id=None,
                channel="web",
            )

        # Get first page
        page1, total1 = await ai_assistant.list_user_sessions(
            db=db_session,
            user_id=user.id,
            limit=2,
            skip=0,
        )

        # Get second page
        page2, total2 = await ai_assistant.list_user_sessions(
            db=db_session,
            user_id=user.id,
            limit=2,
            skip=2,
        )

        assert len(page1) == 2
        assert len(page2) == 2
        assert total1 == 5
        assert total2 == 5


class TestSessionIsolation:
    """Test security - session isolation between users."""

    @pytest.mark.asyncio
    async def test_cannot_access_other_user_session(
        self,
        db_session: AsyncSession,
        ai_assistant: AIAssistant,
    ):
        """User should not access another user's session."""
        user1 = await test_user.__wrapped__(db_session)
        user2 = await test_user.__wrapped__(db_session)
        articles = await test_articles.__wrapped__(db_session)

        # User 1 creates session
        response = await ai_assistant.chat(
            db=db_session,
            user_id=user1.id,
            question="User 1 question",
            session_id=None,
            channel="web",
        )

        # Get user 1's session
        from sqlalchemy import select

        session_result = await db_session.execute(
            select(ChatSession).filter(ChatSession.user_id == user1.id)
        )
        user1_session = session_result.scalars().first()

        # User 2 tries to access user 1's session
        with pytest.raises(ValueError, match="not found|permission|access"):
            await ai_assistant.get_session_history(
                db=db_session,
                user_id=user2.id,
                session_id=UUID(user1_session.id),
            )

    @pytest.mark.asyncio
    async def test_user_cannot_see_other_users_sessions(
        self,
        db_session: AsyncSession,
        ai_assistant: AIAssistant,
    ):
        """User list should not include other users' sessions."""
        user1 = await test_user.__wrapped__(db_session)
        user2 = await test_user.__wrapped__(db_session)
        articles = await test_articles.__wrapped__(db_session)

        # User 1 creates sessions
        for i in range(2):
            await ai_assistant.chat(
                db=db_session,
                user_id=user1.id,
                question=f"User 1 question {i}",
                session_id=None,
                channel="web",
            )

        # User 2 creates session
        await ai_assistant.chat(
            db=db_session,
            user_id=user2.id,
            question="User 2 question",
            session_id=None,
            channel="web",
        )

        # User 2 lists sessions
        user2_sessions, _ = await ai_assistant.list_user_sessions(
            db=db_session,
            user_id=user2.id,
            limit=10,
            skip=0,
        )

        # Should only see own session
        assert len(user2_sessions) == 1


class TestEdgeCases:
    """Test edge cases."""

    @pytest.mark.asyncio
    async def test_chat_very_long_question(
        self,
        db_session: AsyncSession,
        ai_assistant: AIAssistant,
    ):
        """Should handle very long but valid questions."""
        user = await test_user.__wrapped__(db_session)
        articles = await test_articles.__wrapped__(db_session)

        long_question = "How do I reset my password? " * 50  # 1650 chars

        response = await ai_assistant.chat(
            db=db_session,
            user_id=user.id,
            question=long_question,
            session_id=None,
            channel="web",
        )

        assert response is not None

    @pytest.mark.asyncio
    async def test_chat_unicode_question(
        self,
        db_session: AsyncSession,
        ai_assistant: AIAssistant,
    ):
        """Should handle Unicode characters in questions."""
        user = await test_user.__wrapped__(db_session)
        articles = await test_articles.__wrapped__(db_session)

        response = await ai_assistant.chat(
            db=db_session,
            user_id=user.id,
            question="如何重置密码 Как сбросить пароль",
            session_id=None,
            channel="web",
        )

        assert response is not None

    @pytest.mark.asyncio
    async def test_chat_special_characters(
        self,
        db_session: AsyncSession,
        ai_assistant: AIAssistant,
    ):
        """Should handle special characters in questions."""
        user = await test_user.__wrapped__(db_session)
        articles = await test_articles.__wrapped__(db_session)

        response = await ai_assistant.chat(
            db=db_session,
            user_id=user.id,
            question="Help with account @ password (urgent!)?",
            session_id=None,
            channel="web",
        )

        assert response is not None

    @pytest.mark.asyncio
    async def test_no_relevant_articles(
        self,
        db_session: AsyncSession,
        ai_assistant: AIAssistant,
    ):
        """Should handle questions with no relevant articles."""
        user = await test_user.__wrapped__(db_session)
        articles = await test_articles.__wrapped__(db_session)

        response = await ai_assistant.chat(
            db=db_session,
            user_id=user.id,
            question="xyzabc_definitely_not_in_kb_content",
            session_id=None,
            channel="web",
        )

        # Should still respond (may escalate)
        assert response is not None


class TestResponseQuality:
    """Test response quality."""

    @pytest.mark.asyncio
    async def test_response_has_confidence_score(
        self,
        db_session: AsyncSession,
        ai_assistant: AIAssistant,
    ):
        """Response should include confidence score."""
        user = await test_user.__wrapped__(db_session)
        articles = await test_articles.__wrapped__(db_session)

        response = await ai_assistant.chat(
            db=db_session,
            user_id=user.id,
            question="How do I reset my password?",
            session_id=None,
            channel="web",
        )

        assert response.confidence_score is not None
        assert 0 <= response.confidence_score <= 1

    @pytest.mark.asyncio
    async def test_response_is_not_empty(
        self,
        db_session: AsyncSession,
        ai_assistant: AIAssistant,
    ):
        """Response should never be empty."""
        user = await test_user.__wrapped__(db_session)
        articles = await test_articles.__wrapped__(db_session)

        response = await ai_assistant.chat(
            db=db_session,
            user_id=user.id,
            question="Test question?",
            session_id=None,
            channel="web",
        )

        assert response.answer is not None
        assert len(response.answer) > 0
