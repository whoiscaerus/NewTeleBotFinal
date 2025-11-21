"""
Test suite for AI RAG indexer.

Tests semantic search, embedding generation, and index management.

Coverage target: 100% of indexer.py
"""

from datetime import datetime
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai.indexer import EmbeddingGenerator, RAGIndexer
from backend.app.ai.models import KBEmbedding
from backend.app.kb.models import Article, ArticleStatus


@pytest.fixture
def embedding_generator():
    """Create embedding generator."""
    return EmbeddingGenerator()


@pytest_asyncio.fixture
async def test_article(db_session: AsyncSession, test_user) -> Article:
    """Create a test KB article."""
    article = Article(
        id=uuid4(),
        title="How to Reset Password",
        slug="how-to-reset-password",
        content="Click on forgot password and enter your email",
        status=ArticleStatus.PUBLISHED,
        author_id=test_user.id,
        locale="en",
        version=1,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        published_at=datetime.utcnow(),
    )
    db_session.add(article)
    await db_session.commit()
    await db_session.refresh(article)
    return article


@pytest_asyncio.fixture
async def test_articles(db_session: AsyncSession, test_user) -> list[Article]:
    """Create multiple test KB articles."""
    articles = []
    titles = [
        "How to Reset Password",
        "Billing FAQ",
        "Two-Factor Authentication",
        "Account Security",
        "Refund Policy",
    ]
    for title in titles:
        article = Article(
            id=uuid4(),
            title=title,
            slug=title.lower().replace(" ", "-"),
            content=f"Content about {title.lower()}",
            status=ArticleStatus.PUBLISHED,
            author_id=test_user.id,
            locale="en",
            version=1,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            published_at=datetime.utcnow(),
        )
        db_session.add(article)
        articles.append(article)

    await db_session.commit()
    for article in articles:
        await db_session.refresh(article)
    return articles


class TestEmbeddingGenerator:
    """Test embedding generation."""

    @pytest.mark.asyncio
    async def test_generate_embedding(self, embedding_generator):
        """Should generate embedding for text."""
        text = "How to reset password"
        embedding = await embedding_generator.generate(text)

        assert embedding is not None
        assert isinstance(embedding, list)
        assert len(embedding) > 0
        assert all(isinstance(x, float) for x in embedding)

    @pytest.mark.asyncio
    async def test_embedding_deterministic(self, embedding_generator):
        """Same text should produce same embedding (deterministic for testing)."""
        text = "How to reset password"
        embedding1 = await embedding_generator.generate(text)
        embedding2 = await embedding_generator.generate(text)

        assert embedding1 == embedding2

    @pytest.mark.asyncio
    async def test_embedding_different_texts(self, embedding_generator):
        """Different texts should produce different embeddings."""
        text1 = "How to reset password"
        text2 = "Billing information"
        embedding1 = await embedding_generator.generate(text1)
        embedding2 = await embedding_generator.generate(text2)

        assert embedding1 != embedding2

    @pytest.mark.asyncio
    async def test_embedding_normalized(self, embedding_generator):
        """Embeddings should be normalized (values in [-1, 1] range)."""
        text = "Test content for embedding"
        embedding = await embedding_generator.generate(text)

        for value in embedding:
            assert -1 <= value <= 1

    @pytest.mark.asyncio
    async def test_embedding_nonzero(self, embedding_generator):
        """Embeddings should not be all zeros."""
        text = "Test content"
        embedding = await embedding_generator.generate(text)

        assert any(x != 0 for x in embedding)


class TestCosineSimilarity:
    """Test cosine similarity calculation."""

    def test_identical_vectors_similarity_one(self, embedding_generator):
        """Identical vectors should have similarity 1.0."""
        vec = [1.0, 0.0, 0.0]
        similarity = embedding_generator.cosine_similarity(vec, vec)

        assert abs(similarity - 1.0) < 0.0001

    def test_orthogonal_vectors_similarity_zero(self, embedding_generator):
        """Orthogonal vectors should have similarity ~0."""
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [0.0, 1.0, 0.0]
        similarity = embedding_generator.cosine_similarity(vec1, vec2)

        assert abs(similarity) < 0.0001

    def test_opposite_vectors_similarity_negative_one(self, embedding_generator):
        """Opposite vectors should have similarity -1.0."""
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [-1.0, 0.0, 0.0]
        similarity = embedding_generator.cosine_similarity(vec1, vec2)

        assert abs(similarity + 1.0) < 0.0001

    def test_similar_vectors_high_similarity(self, embedding_generator):
        """Similar vectors should have high similarity."""
        vec1 = [1.0, 1.0, 0.0]
        vec2 = [1.0, 0.9, 0.0]
        similarity = embedding_generator.cosine_similarity(vec1, vec2)

        assert 0.99 < similarity < 1.0

    def test_dissimilar_vectors_low_similarity(self, embedding_generator):
        """Dissimilar vectors should have low similarity."""
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [0.0, 1.0, 1.0]
        similarity = embedding_generator.cosine_similarity(vec1, vec2)

        assert similarity < 0.5


class TestRAGIndexerIndexing:
    """Test article indexing."""

    @pytest.mark.asyncio
    async def test_index_article(self, db_session: AsyncSession, test_article):
        """Should index published article and create embedding."""
        article = test_article
        indexer = RAGIndexer()

        result = await indexer.index_article(db_session, article.id)

        assert result is not None
        assert isinstance(result, KBEmbedding)
        assert result.article_id == article.id
        assert result.embedding is not None
        assert len(result.embedding) > 0

    @pytest.mark.asyncio
    async def test_index_article_unpublished_fails(
        self, db_session: AsyncSession, test_user
    ):
        """Should reject indexing unpublished articles."""
        # Create unpublished article
        article = Article(
            id=uuid4(),
            title="Draft Article",
            slug="draft",
            content="Draft content",
            status=ArticleStatus.DRAFT,
            author_id=test_user.id,
            locale="en",
            version=1,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            published_at=None,
        )
        db_session.add(article)
        await db_session.commit()

        indexer = RAGIndexer()
        with pytest.raises(ValueError, match="not published"):
            await indexer.index_article(db_session, article.id)

    @pytest.mark.asyncio
    async def test_index_article_nonexistent_fails(self, db_session: AsyncSession):
        """Should fail gracefully for nonexistent article."""
        indexer = RAGIndexer()
        with pytest.raises(ValueError):
            await indexer.index_article(db_session, uuid4())

    @pytest.mark.asyncio
    async def test_index_article_idempotent(
        self, db_session: AsyncSession, test_article
    ):
        """Indexing same article twice should update, not duplicate."""
        article = test_article
        indexer = RAGIndexer()

        # Index first time
        await indexer.index_article(db_session, article.id)
        stmt = select(KBEmbedding).filter(KBEmbedding.article_id == article.id)
        embeddings1 = await db_session.execute(stmt)
        count1 = len(embeddings1.scalars().all())

        # Index second time
        await indexer.index_article(db_session, article.id)
        stmt = select(KBEmbedding).filter(KBEmbedding.article_id == article.id)
        embeddings2 = await db_session.execute(stmt)
        count2 = len(embeddings2.scalars().all())

        assert count1 == count2 == 1  # Should not duplicate


class TestRAGIndexerBatchIndexing:
    """Test batch indexing."""

    @pytest.mark.asyncio
    async def test_index_all_published(self, db_session: AsyncSession, test_articles):
        """Should index all published articles."""
        articles = test_articles
        indexer = RAGIndexer()

        count = await indexer.index_all_published(db_session)

        assert count == 5
        # Verify all embeddings created
        stmt = select(KBEmbedding)
        embeddings = await db_session.execute(stmt)
        embedding_records = embeddings.scalars().all()
        assert len(embedding_records) == 5

    @pytest.mark.asyncio
    async def test_index_all_skips_unpublished(
        self, db_session: AsyncSession, test_user
    ):
        """Should skip unpublished articles."""
        # Create 5 published articles
        for i in range(5):
            article = Article(
                id=uuid4(),
                title=f"Published {i}",
                slug=f"published-{i}",
                content=f"Content {i}",
                status=ArticleStatus.PUBLISHED,
                author_id=test_user.id,
                locale="en",
                version=1,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                published_at=datetime.utcnow(),
            )
            db_session.add(article)

        # Create 3 unpublished articles
        for i in range(3):
            article = Article(
                id=uuid4(),
                title=f"Draft {i}",
                slug=f"draft-{i}",
                content=f"Draft {i}",
                status=ArticleStatus.DRAFT,
                author_id=test_user.id,
                locale="en",
                version=1,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                published_at=None,
            )
            db_session.add(article)

        await db_session.commit()

        indexer = RAGIndexer()
        count = await indexer.index_all_published(db_session)

        assert count == 5  # Only published


class TestRAGIndexerSearch:
    """Test semantic search."""

    @pytest.mark.asyncio
    async def test_search_similar_returns_results(
        self, db_session: AsyncSession, test_articles
    ):
        """Should return similar articles for query."""
        articles = test_articles
        indexer = RAGIndexer()
        await indexer.index_all_published(db_session)

        # Search for something
        results = await indexer.search_similar(db_session, "password reset", top_k=5)

        assert len(results) > 0
        for result in results:
            assert "article_id" in result
            assert "title" in result
            assert "similarity_score" in result

    @pytest.mark.asyncio
    async def test_search_similar_ranked_by_score(
        self, db_session: AsyncSession, test_articles
    ):
        """Results should be ranked by similarity score."""
        articles = test_articles
        indexer = RAGIndexer()
        await indexer.index_all_published(db_session)

        results = await indexer.search_similar(db_session, "password reset", top_k=5)

        # Should be sorted descending
        scores = [r["similarity_score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_search_respects_top_k(self, db_session: AsyncSession, test_articles):
        """Should return at most top_k results."""
        articles = test_articles
        indexer = RAGIndexer()
        await indexer.index_all_published(db_session)

        results = await indexer.search_similar(db_session, "account", top_k=2)

        assert len(results) <= 2

    @pytest.mark.asyncio
    async def test_search_respects_min_score(
        self, db_session: AsyncSession, test_articles
    ):
        """Should filter results below min_score threshold."""
        articles = test_articles
        indexer = RAGIndexer()
        await indexer.index_all_published(db_session)

        # Search with low similarity articles
        results = await indexer.search_similar(
            db_session,
            "xyz_nonsense_query",
            top_k=5,
            min_score=0.9,  # Very high threshold
        )

        # Should have few or no results (unless very similar by chance)
        for result in results:
            assert result["similarity_score"] >= 0.9

    @pytest.mark.asyncio
    async def test_search_empty_index(self, db_session: AsyncSession):
        """Should return empty list if no articles indexed."""
        indexer = RAGIndexer()

        results = await indexer.search_similar(db_session, "anything", top_k=5)

        assert results == []

    @pytest.mark.asyncio
    async def test_search_nonexistent_query(
        self, db_session: AsyncSession, test_articles
    ):
        """Should handle queries with no similar articles gracefully."""
        articles = test_articles
        indexer = RAGIndexer()
        await indexer.index_all_published(db_session)

        results = await indexer.search_similar(
            db_session,
            "xyzabc_definitely_not_in_kb",
            top_k=5,
            min_score=0.5,
        )

        # May return empty or low-scoring results
        assert isinstance(results, list)


class TestRAGIndexerStatus:
    """Test index status reporting."""

    @pytest.mark.asyncio
    async def test_index_status_empty(self, db_session: AsyncSession):
        """Should report zero for empty index."""
        indexer = RAGIndexer()

        status = await indexer.get_index_status(db_session)

        assert status["total_articles"] == 0
        assert status["indexed_articles"] == 0
        assert status["pending_articles"] == 0

    @pytest.mark.asyncio
    async def test_index_status_with_articles(
        self, db_session: AsyncSession, test_user
    ):
        """Should report correct status with articles."""
        # Create articles
        for i in range(5):
            article = Article(
                id=uuid4(),
                title=f"Article {i}",
                slug=f"article-{i}",
                content=f"Content {i}",
                status=ArticleStatus.PUBLISHED,
                author_id=test_user.id,
                locale="en",
                version=1,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                published_at=datetime.utcnow(),
            )
            db_session.add(article)

        await db_session.commit()
        indexer = RAGIndexer()

        status = await indexer.get_index_status(db_session)

        assert status["total_articles"] == 5
        assert status["indexed_articles"] == 0
        assert status["pending_articles"] == 5

    @pytest.mark.asyncio
    async def test_index_status_after_indexing(
        self, db_session: AsyncSession, test_articles
    ):
        """Should update status after indexing."""
        articles = test_articles
        indexer = RAGIndexer()

        # Before indexing
        status_before = await indexer.get_index_status(db_session)
        assert status_before["indexed_articles"] == 0

        # Index all
        await indexer.index_all_published(db_session)

        # After indexing
        status_after = await indexer.get_index_status(db_session)
        assert status_after["indexed_articles"] == 5
        assert status_after["pending_articles"] == 0

    @pytest.mark.asyncio
    async def test_index_status_has_metadata(self, db_session: AsyncSession):
        """Status should include model and timestamp metadata."""
        indexer = RAGIndexer()

        status = await indexer.get_index_status(db_session)

        assert "embedding_model" in status
        assert "last_indexed_at" in status
        assert (
            status["embedding_model"] is not None
            or status["embedding_model"] == "mock-embed-v1"
        )


class TestRAGIndexerEdgeCases:
    """Test edge cases."""

    @pytest.mark.asyncio
    async def test_search_empty_query(self, db_session: AsyncSession, test_articles):
        """Should handle empty query string."""
        articles = test_articles
        indexer = RAGIndexer()
        await indexer.index_all_published(db_session)

        # Should not crash with empty query
        results = await indexer.search_similar(db_session, "", top_k=5)
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_search_very_long_query(
        self, db_session: AsyncSession, test_articles
    ):
        """Should handle very long query."""
        articles = test_articles
        indexer = RAGIndexer()
        await indexer.index_all_published(db_session)

        long_query = "test " * 1000
        results = await indexer.search_similar(db_session, long_query, top_k=5)

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_search_special_characters(
        self, db_session: AsyncSession, test_articles
    ):
        """Should handle queries with special characters."""
        articles = test_articles
        indexer = RAGIndexer()
        await indexer.index_all_published(db_session)

        query = "test!@#$%^&*()"
        results = await indexer.search_similar(db_session, query, top_k=5)

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_search_unicode_query(self, db_session: AsyncSession, test_articles):
        """Should handle Unicode in queries."""
        articles = test_articles
        indexer = RAGIndexer()
        await indexer.index_all_published(db_session)

        query = "你好世界 مرحبا"
        results = await indexer.search_similar(db_session, query, top_k=5)

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_index_article_with_empty_content(
        self, db_session: AsyncSession, test_user
    ):
        """Should handle articles with empty content."""
        article = Article(
            id=uuid4(),
            title="Empty Article",
            slug="empty",
            content="",
            status=ArticleStatus.PUBLISHED,
            author_id=test_user.id,
            locale="en",
            version=1,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            published_at=datetime.utcnow(),
        )
        db_session.add(article)
        await db_session.commit()

        indexer = RAGIndexer()
        result = await indexer.index_article(db_session, article.id)

        assert result is not None
        assert isinstance(result, KBEmbedding)
