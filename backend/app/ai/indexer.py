"""
AI Indexer - RAG (Retrieval-Augmented Generation) indexer for KB articles.

Builds and manages embeddings for semantic search over knowledge base.
"""

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai.models import KBEmbedding
from backend.app.kb.models import Article, ArticleStatus

logger = logging.getLogger(__name__)


class EmbeddingGenerator:
    """Generates embeddings for text (mock implementation, uses random vectors in tests)."""

    def __init__(
        self,
        model_name: str = "openai-text-embedding-3-small",
        embedding_dim: int = 1536,
    ):
        """
        Initialize embedding generator.

        Args:
            model_name: Name of embedding model
            embedding_dim: Dimension of embedding vectors
        """
        self.model_name = model_name
        self.embedding_dim = embedding_dim

    async def generate(self, text: str) -> list[float]:
        """
        Generate embedding for text.

        In production, this would call OpenAI API or similar.
        For testing, returns deterministic embedding based on text hash.

        Args:
            text: Text to embed

        Returns:
            Embedding vector
        """
        # In production, call OpenAI embeddings API
        # For now, create deterministic mock embedding from text hash
        import hashlib

        hash_obj = hashlib.sha256(text.encode())
        hash_int = int(hash_obj.hexdigest(), 16)

        # Generate deterministic but varied embedding from hash
        embedding = []
        for i in range(self.embedding_dim):
            seed_val = (hash_int + i) % 1000000
            # Normalize to [-1, 1]
            val = 2.0 * (seed_val / 1000000) - 1.0
            embedding.append(float(val))

        return embedding

    @staticmethod
    def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
        """
        Compute cosine similarity between two vectors.

        Args:
            vec1: First vector
            vec2: Second vector

        Returns:
            Cosine similarity score [0, 1]
        """
        import math

        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = math.sqrt(sum(a**2 for a in vec1))
        magnitude2 = math.sqrt(sum(a**2 for a in vec2))

        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0

        return dot_product / (magnitude1 * magnitude2)


class RAGIndexer:
    """Manages RAG index for KB articles."""

    def __init__(self, embedding_generator: EmbeddingGenerator | None = None):
        """
        Initialize indexer.

        Args:
            embedding_generator: Optional custom embedding generator (for testing)
        """
        self.embedding_gen = embedding_generator or EmbeddingGenerator()

    async def index_article(self, db: AsyncSession, article_id: UUID) -> KBEmbedding:
        """
        Index a single KB article.

        Args:
            db: Database session
            article_id: ID of article to index

        Returns:
            Created KBEmbedding record

        Raises:
            ValueError: If article not found or not published
        """
        # Fetch article
        result = await db.execute(select(Article).where(Article.id == article_id))
        article = result.scalar_one_or_none()

        if not article:
            raise ValueError(f"Article {article_id} not found")

        if article.status != ArticleStatus.PUBLISHED:
            raise ValueError(f"Article {article_id} is not published")

        # Generate embedding from article content
        # Combine title + content for richer semantic representation
        text_to_embed = f"{article.title}\n\n{article.content}"
        embedding_vec = await self.embedding_gen.generate(text_to_embed)

        # Check if embedding already exists
        existing = await db.execute(
            select(KBEmbedding).where(KBEmbedding.article_id == article_id)
        )
        kb_embedding = existing.scalar_one_or_none()

        if kb_embedding:
            # Update existing
            kb_embedding.embedding = embedding_vec
            kb_embedding.updated_at = __import__("datetime").datetime.utcnow()
            logger.info(f"Updated embedding for article {article_id}")
        else:
            # Create new
            kb_embedding = KBEmbedding(
                article_id=article_id,
                embedding=embedding_vec,
                embedding_model=self.embedding_gen.model_name,
            )
            db.add(kb_embedding)
            logger.info(f"Created embedding for article {article_id}")

        await db.commit()
        await db.refresh(kb_embedding)
        return kb_embedding

    async def index_all_published(self, db: AsyncSession) -> int:
        """
        Index all published KB articles.

        Args:
            db: Database session

        Returns:
            Number of articles indexed/updated
        """
        # Get all published articles
        result = await db.execute(
            select(Article).where(Article.status == ArticleStatus.PUBLISHED)
        )
        articles = result.scalars().all()

        count = 0
        for article in articles:
            try:
                await self.index_article(db, article.id)
                count += 1
            except Exception as e:
                logger.error(f"Failed to index article {article.id}: {e}")

        logger.info(f"Indexed {count}/{len(articles)} articles")
        return count

    async def search_similar(
        self, db: AsyncSession, query_text: str, top_k: int = 5, min_score: float = 0.3
    ) -> list[dict[str, Any]]:
        """
        Search for similar KB articles using semantic similarity.

        Args:
            db: Database session
            query_text: Question/search query
            top_k: Number of results to return
            min_score: Minimum similarity score (0-1) to include results

        Returns:
            List of dicts with article_id, title, excerpt, similarity_score
        """
        # Generate query embedding
        query_embedding = await self.embedding_gen.generate(query_text)

        # Get all indexed articles
        result = await db.execute(select(KBEmbedding))
        kb_embeddings = result.scalars().all()

        if not kb_embeddings:
            return []

        # Compute similarity scores
        similarities: list[tuple[KBEmbedding, float]] = []
        for kb_emb in kb_embeddings:
            score = self.embedding_gen.cosine_similarity(
                query_embedding, kb_emb.embedding
            )
            if score >= min_score:
                similarities.append((kb_emb, score))

        # Sort by score descending
        similarities.sort(key=lambda x: x[1], reverse=True)

        # Get top-k results with article details
        results = []
        for kb_emb, score in similarities[:top_k]:
            # Fetch article details
            article_result = await db.execute(
                select(Article).where(Article.id == kb_emb.article_id)
            )
            article = article_result.scalar_one_or_none()

            if article:
                # Extract excerpt (first 200 chars)
                excerpt = (
                    article.content[:200] + "..."
                    if len(article.content) > 200
                    else article.content
                )
                results.append(
                    {
                        "article_id": str(article.id),
                        "title": article.title,
                        "excerpt": excerpt,
                        "similarity_score": float(score),
                        "url": f"/kb/{article.slug}",
                        "locale": article.locale,
                    }
                )

        return results

    async def get_index_status(self, db: AsyncSession) -> dict[str, Any]:
        """
        Get status of RAG index.

        Args:
            db: Database session

        Returns:
            Index status dict
        """
        # Count published articles
        pub_result = await db.execute(
            select(Article).where(Article.status == ArticleStatus.PUBLISHED)
        )
        total_articles = len(pub_result.scalars().all())

        # Count indexed embeddings
        emb_result = await db.execute(select(KBEmbedding))
        indexed_articles = len(emb_result.scalars().all())

        # Get last indexed time
        ordered_result = await db.execute(
            select(KBEmbedding).order_by(KBEmbedding.indexed_at.desc()).limit(1)
        )
        last_emb = ordered_result.scalar_one_or_none()

        return {
            "total_articles": total_articles,
            "indexed_articles": indexed_articles,
            "pending_articles": total_articles - indexed_articles,
            "last_indexed_at": last_emb.indexed_at if last_emb else None,
            "embedding_model": last_emb.embedding_model if last_emb else "unknown",
        }
