"""
Knowledge Base CMS Module

Lightweight CMS for authoring articles, FAQs, and lessons used by Education Hub and AI support.
Supports versioning, localization, approvals, and view tracking.
"""

from backend.app.kb.models import (
    Article,
    ArticleAttachment,
    ArticleStatus,
    ArticleTag,
    ArticleVersion,
    ArticleView,
    Tag,
)
from backend.app.kb.routes import router
from backend.app.kb.service import KnowledgeBaseService

__all__ = [
    "Article",
    "ArticleStatus",
    "Tag",
    "ArticleTag",
    "ArticleVersion",
    "ArticleAttachment",
    "ArticleView",
    "KnowledgeBaseService",
    "router",
]
