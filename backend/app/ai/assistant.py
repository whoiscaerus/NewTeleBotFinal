"""
AI Assistant - Main RAG-powered chat assistant service.

Orchestrates:
- Session management
- RAG retrieval
- Guardrails checking
- Response generation
- Citation tracking
"""

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.ai.guardrails import AIGuardrails
from backend.app.ai.indexer import RAGIndexer
from backend.app.ai.models import ChatMessage, ChatMessageRole, ChatSession
from backend.app.ai.schemas import ChatCitation, ChatResponseOut

logger = logging.getLogger(__name__)


class AIAssistant:
    """Main AI assistant for customer support."""

    def __init__(
        self, indexer: RAGIndexer | None = None, guardrails: AIGuardrails | None = None
    ):
        """
        Initialize assistant.

        Args:
            indexer: RAG indexer instance
            guardrails: Safety guardrails instance
        """
        self.indexer = indexer or RAGIndexer()
        self.guardrails = guardrails or AIGuardrails()

    async def chat(
        self,
        db: AsyncSession,
        user_id: UUID,
        question: str,
        session_id: UUID | None = None,
        channel: str = "web",
    ) -> ChatResponseOut:
        """
        Process user question and generate response.

        Args:
            db: Database session
            user_id: ID of user asking question
            question: User's question/message
            session_id: Existing session ID (optional, creates new if None)
            channel: Channel (telegram/web)

        Returns:
            ChatResponseOut with response, citations, etc.

        Raises:
            ValueError: If input validation fails
        """
        # 1. Validate input
        input_check = self.guardrails.check_input(question)
        if input_check.blocked:
            logger.warning(
                f"Input blocked: {input_check.reason}", extra={"user_id": str(user_id)}
            )
            raise ValueError(f"Invalid input: {input_check.reason}")

        # 2. Create or fetch session
        if session_id:
            result = await db.execute(
                select(ChatSession).where(
                    ChatSession.id == session_id, ChatSession.user_id == user_id
                )
            )
            session = result.scalar_one_or_none()
            if not session:
                raise ValueError(f"Session {session_id} not found or not owned by user")
        else:
            # Create new session
            session = ChatSession(user_id=user_id, title=question[:100])
            db.add(session)
            await db.flush()

        # Check if already escalated
        if session.escalated:
            # Don't answer, suggest human support
            return ChatResponseOut(
                session_id=session.id,
                message_id=UUID(int=0),  # Placeholder
                answer="This conversation has been escalated to our support team. A human agent will respond shortly.",
                requires_escalation=False,
                confidence_score=0.0,
                blocked_by_policy="session_escalated",
            )

        # 3. Store user message
        user_msg = ChatMessage(
            session_id=session.id,
            role=ChatMessageRole.USER,
            content=question,
        )
        db.add(user_msg)
        await db.flush()

        logger.info(
            "Processing chat question",
            extra={
                "user_id": str(user_id),
                "session_id": str(session.id),
                "channel": channel,
            },
        )

        # 4. Retrieve relevant KB articles (RAG)
        similar_articles = await self.indexer.search_similar(
            db, question, top_k=5, min_score=0.3
        )

        if not similar_articles:
            # No relevant articles found
            response_text = (
                "I couldn't find relevant articles to answer your question. "
                "Please contact our support team for assistance."
            )
            citations = []
            requires_escalation = True
            escalation_reason = "No relevant KB articles found"
        else:
            # 5. Generate response from context
            context = "\n\n".join(
                [
                    f"Title: {art['title']}\n{art['excerpt']}"
                    for art in similar_articles[:3]
                ]
            )

            # Build response (in production, would use LLM like GPT-4)
            # For now, use template-based response
            response_text = await self._generate_response(question, context)

            # 6. Run guardrails on response
            output_check = self.guardrails.check_output(response_text)

            if output_check.blocked:
                # Response violated policy - escalate
                logger.warning(
                    "Response blocked by guardrails",
                    extra={
                        "user_id": str(user_id),
                        "policy": output_check.policy_name,
                    },
                )
                sanitized_text = output_check.redacted_text or response_text
                blocked_policy = output_check.policy_name
                response_text = (
                    "I'm unable to provide an answer to your question. "
                    "An agent will review your request shortly."
                )
                citations = []
                requires_escalation = True
                escalation_reason = blocked_policy
            else:
                # Response is safe - use redacted version if available
                sanitized_text = output_check.redacted_text or response_text
                response_text = sanitized_text
                citations = [
                    ChatCitation(
                        article_id=UUID(art["article_id"]),
                        title=art["title"],
                        url=art["url"],
                        excerpt=art["excerpt"],
                    )
                    for art in similar_articles[:3]
                ]
                requires_escalation = False
                escalation_reason = None

        # 7. Store AI response
        # Convert citations to dict with string UUIDs for JSON serialization
        citations_data = [
            {
                "article_id": str(c.article_id),
                "title": c.title,
                "url": c.url,
                "excerpt": c.excerpt,
            }
            for c in citations
        ]

        assistant_msg = ChatMessage(
            session_id=session.id,
            role=ChatMessageRole.ASSISTANT,
            content=response_text,
            citations=citations_data,
            blocked_by_policy=escalation_reason if requires_escalation else None,
            confidence_score=0.85 if similar_articles else 0.0,
        )
        db.add(assistant_msg)

        # 8. Handle escalation if needed
        if requires_escalation:
            session.escalated = True
            session.escalated_to_human_at = datetime.utcnow()
            session.escalation_reason = escalation_reason
            logger.info(
                "Chat escalated to human",
                extra={
                    "user_id": str(user_id),
                    "session_id": str(session.id),
                    "reason": escalation_reason,
                },
            )

        await db.commit()
        await db.refresh(assistant_msg)

        # 9. Build response
        return ChatResponseOut(
            session_id=session.id,
            message_id=assistant_msg.id,
            answer=response_text,
            citations=citations,
            confidence_score=assistant_msg.confidence_score or 0.0,
            blocked_by_policy=None if not requires_escalation else escalation_reason,
            requires_escalation=requires_escalation,
            escalation_reason=escalation_reason,
        )

    async def _generate_response(self, question: str, context: str) -> str:
        """
        Generate response text from context.

        In production, this would call an LLM. For now, uses template-based generation.

        Args:
            question: User's question
            context: Retrieved KB context

        Returns:
            Generated response text
        """
        # Simple template-based response for demo
        # In production: prompt_template + LLM.generate()
        return (
            f"Based on our documentation:\n\n{context}\n\n"
            f"To better assist you, could you provide more details about: {question}?"
        )

    async def get_session_history(
        self, db: AsyncSession, user_id: UUID, session_id: UUID
    ) -> dict[str, Any]:
        """
        Get full chat history for a session.

        Args:
            db: Database session
            user_id: User ID (for ownership verification)
            session_id: Session ID

        Returns:
            Session with messages

        Raises:
            ValueError: If session not found or not owned by user
        """
        result = await db.execute(
            select(ChatSession)
            .where(ChatSession.id == session_id, ChatSession.user_id == user_id)
            .options(selectinload(ChatSession.messages))
        )
        session = result.scalar_one_or_none()

        if not session:
            raise ValueError("Session not found")

        return {
            "session": {
                "id": str(session.id),
                "title": session.title,
                "escalated": session.escalated,
                "escalation_reason": session.escalation_reason,
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat(),
            },
            "messages": [
                {
                    "id": str(msg.id),
                    "role": msg.role,
                    "content": msg.content,
                    "citations": msg.citations,
                    "created_at": msg.created_at.isoformat(),
                }
                for msg in session.messages
            ],
        }

    async def escalate_to_human(
        self,
        db: AsyncSession,
        user_id: UUID,
        session_id: UUID,
        reason: str,
    ) -> None:
        """
        Manually escalate a session to human support.

        Args:
            db: Database session
            user_id: User ID (for ownership verification)
            session_id: Session ID
            reason: Escalation reason

        Raises:
            ValueError: If session not found or not owned by user
        """
        result = await db.execute(
            select(ChatSession).where(
                ChatSession.id == session_id, ChatSession.user_id == user_id
            )
        )
        session = result.scalar_one_or_none()

        if not session:
            raise ValueError("Session not found")

        session.escalated = True
        session.escalated_to_human_at = datetime.utcnow()
        session.escalation_reason = reason

        await db.commit()
        logger.info(
            "Session manually escalated",
            extra={
                "user_id": str(user_id),
                "session_id": str(session_id),
                "reason": reason,
            },
        )

    async def list_user_sessions(
        self, db: AsyncSession, user_id: UUID, limit: int = 50, skip: int = 0
    ) -> tuple[list[dict[str, Any]], int]:
        """
        List all chat sessions for a user.

        Args:
            db: Database session
            user_id: User ID
            limit: Pagination limit
            skip: Pagination skip

        Returns:
            (list of sessions, total count)
        """
        from sqlalchemy import desc, func

        # Get total count
        count_result = await db.execute(
            select(func.count(ChatSession.id)).where(ChatSession.user_id == user_id)
        )
        total = count_result.scalar() or 0

        # Get paginated sessions with message counts
        from sqlalchemy.orm import selectinload

        result = await db.execute(
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .options(selectinload(ChatSession.messages))
            .order_by(desc(ChatSession.updated_at))
            .limit(limit)
            .offset(skip)
        )
        sessions = result.scalars().all()

        return (
            [
                {
                    "id": str(s.id),
                    "title": s.title,
                    "escalated": s.escalated,
                    "message_count": len(s.messages),
                    "created_at": s.created_at.isoformat(),
                    "updated_at": s.updated_at.isoformat(),
                }
                for s in sessions
            ],
            total,
        )
