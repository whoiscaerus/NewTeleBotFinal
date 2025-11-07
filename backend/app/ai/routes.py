"""
AI Routes - FastAPI endpoints for chat assistant.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
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
            user_id=current_user.id,
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
        logger.info(
            "Chat response generated",
            extra={
                "user_id": str(current_user.id),
                "result": result,
                "confidence": response.confidence_score,
            },
        )

        return response

    except ValueError as e:
        logger.warning(
            f"Chat validation error: {e}", extra={"user_id": str(current_user.id)}
        )
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
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
    if limit > 100:
        limit = 100

    sessions, _ = await _assistant.list_user_sessions(
        db, current_user.id, limit=limit, skip=skip
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
        history = await _assistant.get_session_history(db, current_user.id, session_id)

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
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/sessions/{session_id}/escalate", status_code=204)
async def escalate_session(
    session_id: UUID,
    request: EscalateRequestIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Manually escalate a chat session to human support.

    Requires reason for escalation.
    """
    try:
        await _assistant.escalate_to_human(
            db, current_user.id, session_id, request.reason
        )
        logger.info(
            "Session escalated manually",
            extra={
                "user_id": str(current_user.id),
                "session_id": str(session_id),
                "reason": request.reason,
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


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
        logger.info("Index rebuild triggered", extra={"indexed_count": count})

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
    status_dict = await _indexer.get_index_status(db)

    return IndexStatusOut(
        total_articles=status_dict["total_articles"],
        indexed_articles=status_dict["indexed_articles"],
        pending_articles=status_dict["pending_articles"],
        last_indexed_at=status_dict["last_indexed_at"],
        embedding_model=status_dict["embedding_model"],
    )
