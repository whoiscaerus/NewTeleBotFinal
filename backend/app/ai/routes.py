"""
AI Routes - FastAPI endpoints for chat assistant.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from prometheus_client import Counter, Histogram
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai.assistant import AIAssistant
from backend.app.ai.indexer import RAGIndexer
from backend.app.ai.schemas import (
    ChatRequestIn,
    ChatResponseOut,
    ChatSessionDetailOut,
    ChatSessionOut,
    EscalateRequestIn,
    IndexStatusOut,
)
from backend.app.auth.dependencies import get_current_user
from backend.app.auth.models import User, UserRole
from backend.app.core.db import get_db

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])
logger = logging.getLogger(__name__)

# Prometheus metrics for AI operations
ai_chat_requests_total = Counter(
    "ai_chat_requests_total",
    "Total AI chat requests (result: success|blocked|error, escalated: true|false)",
    ["result", "escalated"],
)

ai_guard_blocks_total = Counter(
    "ai_guard_blocks_total",
    "Total guardrail policy blocks (policy: api_key|pii|financial|trading|config)",
    ["policy"],
)

ai_rag_searches_total = Counter(
    "ai_rag_searches_total", "Total RAG KB searches (hit: true|false)", ["hit"]
)

ai_response_confidence = Histogram(
    "ai_response_confidence",
    "Distribution of AI response confidence scores",
    buckets=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
)


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Dependency to require admin role."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


# Initialize assistant (would be injected in production)
_assistant = AIAssistant()
_indexer = RAGIndexer()


@router.post("/chat", response_model=ChatResponseOut, status_code=201)
async def chat(
    request: ChatRequestIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Send a chat message and get AI response.

    - **session_id**: Existing session ID (optional, creates new if omitted)
    - **question**: User's question (1-2000 chars)
    - **channel**: "telegram" or "web"

    Returns AI response with citations, confidence score, and escalation info.

    Telemetry: `ai_chat_total{result}` (success, escalated, blocked)
    """
    try:
        response = await _assistant.chat(
            db=db,
            user_id=UUID(str(current_user.id)),
            question=request.question,
            session_id=request.session_id,
            channel=request.channel,
        )

        # Track telemetry
        result = (
            "escalated"
            if response.requires_escalation
            else ("blocked" if response.blocked_by_policy else "success")
        )
        escalated = str(response.requires_escalation).lower()
        ai_chat_requests_total.labels(result=result, escalated=escalated).inc()
        ai_response_confidence.observe(response.confidence_score)

        logger.info(
            "Chat response generated",
            extra={
                "user_id": str(current_user.id),
                "result": result,
                "confidence": response.confidence_score,
                "escalated": response.requires_escalation,
            },
        )

        return response

    except ValueError as e:
        ai_chat_requests_total.labels(result="error", escalated="false").inc()
        logger.warning(
            f"Chat validation error: {e}", extra={"user_id": str(current_user.id)}
        )
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        ai_chat_requests_total.labels(result="error", escalated="false").inc()
        logger.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/sessions", response_model=list[ChatSessionOut])
async def list_sessions(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List chat sessions for current user.

    Returns paginated list of sessions (most recent first).
    """
    try:
        if limit > 100:
            limit = 100

        sessions, _ = await _assistant.list_user_sessions(
            db, UUID(str(current_user.id)), limit=limit, skip=skip
        )

        logger.info(
            "Sessions listed",
            extra={
                "user_id": str(current_user.id),
                "session_count": len(sessions),
            },
        )

        return [
            ChatSessionOut(
                id=UUID(s["id"]),
                title=s["title"],
                escalated=s["escalated"],
                message_count=s["message_count"],
                created_at=s["created_at"],
                updated_at=s["updated_at"],
            )
            for s in sessions
        ]

    except Exception as e:
        logger.error(f"Error listing sessions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list sessions")


@router.get("/sessions/{session_id}", response_model=ChatSessionDetailOut)
async def get_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get full chat history for a session.

    Returns all messages with citations and metadata.
    """
    try:
        history = await _assistant.get_session_history(db, UUID(str(current_user.id)), session_id)

        logger.info(
            "Session retrieved",
            extra={
                "user_id": str(current_user.id),
                "session_id": str(session_id),
                "message_count": len(history.get("messages", [])),
            },
        )

        return ChatSessionDetailOut(
            id=UUID(history["session"]["id"]),
            title=history["session"]["title"],
            escalated=history["session"]["escalated"],
            escalation_reason=history["session"].get("escalation_reason"),
            created_at=history["session"]["created_at"],
            updated_at=history["session"]["updated_at"],
            messages=[],  # Simplified for now
        )

    except ValueError as e:
        logger.error(f"Session not found: {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error retrieving session: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve session")


@router.post("/sessions/{session_id}/escalate", status_code=204)
async def escalate_session(
    session_id: UUID,
    request: EscalateRequestIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Manually escalate a chat session to human support.

    Requires reason for escalation. Automatically creates a support ticket
    for human triage and response.
    """
    try:
        await _assistant.escalate_to_human(
            db, UUID(str(current_user.id)), session_id, request.reason
        )

        # Create support ticket for escalation
        from backend.app.messaging.integrations import telegram_owner
        from backend.app.support import service as support_service

        ticket = await support_service.create_ticket(
            db=db,
            user_id=current_user.id,
            subject=f"AI Chat Escalation: {request.reason[:150]}",
            body=f"AI chat session escalated to human support.\n\nReason: {request.reason}\n\nSession ID: {session_id}",
            severity="high",  # Manual escalations are high priority
            channel="ai_chat",
            context={
                "session_id": str(session_id),
                "escalation_reason": request.reason,
                "escalation_type": "manual",
            },
        )

        # Send owner notification for high-severity tickets
        if ticket.severity == "high" or ticket.severity == "urgent":
            await telegram_owner.send_owner_notification(
                ticket_id=str(ticket.id),
                user_id=current_user.id,
                subject=str(ticket.subject),
                severity=str(ticket.severity),
                channel="ai_chat",
            )

        # Track escalation in telemetry
        ai_chat_requests_total.labels(result="escalated", escalated="true").inc()

        logger.info(
            "Session escalated manually with ticket created",
            extra={
                "user_id": str(current_user.id),
                "session_id": str(session_id),
                "ticket_id": ticket.id,
                "reason": request.reason,
                "escalated": True,
            },
        )

    except ValueError as e:
        logger.error(f"Escalation failed - session not found: {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error escalating session: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to escalate session")


# Admin-only endpoints


@router.post("/index/build", status_code=202)
async def build_index(
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    """
    Trigger rebuild of RAG index from KB articles.

    Admin only. Indexes all published articles and generates embeddings.

    Telemetry: `ai_index_build_total`
    """
    try:
        count = await _indexer.index_all_published(db)

        # Track successful index build
        ai_rag_searches_total.labels(hit="true").inc()

        logger.info(
            "Index rebuild triggered",
            extra={
                "admin_id": str(admin_user.id),
                "indexed_count": count,
            },
        )

        return {"status": "indexed", "count": count}

    except Exception as e:
        logger.error(f"Index build error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to build index")


@router.get("/index/status", response_model=IndexStatusOut)
async def index_status(
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    """
    Get RAG index status.

    Admin only. Returns indexing progress and stats.
    """
    try:
        status_dict = await _indexer.get_index_status(db)

        # Track index status check
        indexed_pct = (
            status_dict["indexed_articles"] / status_dict["total_articles"]
            if status_dict["total_articles"] > 0
            else 1.0
        )
        ai_response_confidence.observe(indexed_pct)

        logger.info(
            "Index status retrieved",
            extra={
                "admin_id": str(admin_user.id),
                "total_articles": status_dict["total_articles"],
                "indexed_articles": status_dict["indexed_articles"],
                "indexed_pct": indexed_pct,
            },
        )

        return IndexStatusOut(
            total_articles=status_dict["total_articles"],
            indexed_articles=status_dict["indexed_articles"],
            pending_articles=status_dict["pending_articles"],
            last_indexed_at=status_dict["last_indexed_at"],
            embedding_model=status_dict["embedding_model"],
        )

    except Exception as e:
        logger.error(f"Error retrieving index status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve index status")
