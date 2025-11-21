"""
Comprehensive Tests for PR-069: Internationalization & Copy Registry

Tests validate:
1. Copy entry CRUD operations
2. Copy variant management
3. A/B testing impression/conversion tracking
4. Copy resolution with locale fallback
5. Missing key detection
6. Database integrity and cascade deletion
"""

import pytest
from pytest_asyncio import fixture as asyncio_fixture
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.copy.models import CopyEntry, CopyStatus, CopyType, CopyVariant
from backend.app.copy.schemas import CopyEntryCreate, CopyEntryUpdate, CopyVariantCreate
from backend.app.copy.service import CopyService

# --- Fixtures ---


@asyncio_fixture
async def copy_service(db_session: AsyncSession) -> CopyService:
    """Provide copy service with test database."""
    return CopyService(db_session)


@asyncio_fixture
async def sample_entry(copy_service: CopyService) -> CopyEntry:
    """Create a sample copy entry for testing."""
    data = CopyEntryCreate(
        key="hero.title",
        type=CopyType.MARKETING,
        description="Main hero heading",
        metadata={"section": "landing"},
        variants=[
            CopyVariantCreate(
                locale="en",
                is_control=True,
                text="Professional Trading Signals",
                metadata={},
            ),
            CopyVariantCreate(
                locale="es",
                is_control=True,
                text="Señales de Trading Profesionales",
                metadata={},
            ),
        ],
    )
    return await copy_service.create_entry(data, user_id="test-user")


# --- Test Copy Entry Creation ---


@pytest.mark.asyncio
async def test_create_copy_entry_with_variants(copy_service: CopyService):
    """Test creating copy entry with multiple locale variants."""
    data = CopyEntryCreate(
        key="cta.signup",
        type=CopyType.PRODUCT,
        description="Sign up CTA button",
        variants=[
            CopyVariantCreate(locale="en", text="Sign Up", is_control=True),
            CopyVariantCreate(locale="es", text="Registrarse", is_control=True),
        ],
    )

    entry = await copy_service.create_entry(data, user_id="admin-123")

    assert entry.id is not None
    assert entry.key == "cta.signup"
    assert entry.type == CopyType.PRODUCT
    assert entry.status == CopyStatus.DRAFT
    assert entry.created_by == "admin-123"
    assert len(entry.variants) == 2

    # Verify variant details
    en_variant = next(v for v in entry.variants if v.locale == "en")
    assert en_variant.text == "Sign Up"
    assert en_variant.is_control is True
    assert en_variant.impressions == 0

    es_variant = next(v for v in entry.variants if v.locale == "es")
    assert es_variant.text == "Registrarse"


@pytest.mark.asyncio
async def test_cannot_create_duplicate_key(copy_service: CopyService):
    """Test that duplicate keys are rejected."""
    data = CopyEntryCreate(
        key="unique.key",
        type=CopyType.PRODUCT,
        variants=[CopyVariantCreate(locale="en", text="Text")],
    )

    # First creation succeeds
    await copy_service.create_entry(data)

    # Second creation with same key fails
    with pytest.raises(ValueError, match="already exists"):
        await copy_service.create_entry(data)


@pytest.mark.asyncio
async def test_create_entry_without_variants(copy_service: CopyService):
    """Test creating entry without initial variants (allowed)."""
    data = CopyEntryCreate(key="empty.entry", type=CopyType.PRODUCT, variants=[])

    entry = await copy_service.create_entry(data)

    assert entry.id is not None
    assert len(entry.variants) == 0


# --- Test Copy Entry Updates ---


@pytest.mark.asyncio
async def test_update_entry_metadata(
    copy_service: CopyService, sample_entry: CopyEntry
):
    """Test updating copy entry metadata."""
    update_data = CopyEntryUpdate(
        description="Updated description",
        metadata={"section": "landing", "priority": "high"},
    )

    updated = await copy_service.update_entry(
        sample_entry.id, update_data, user_id="editor-456"
    )

    assert updated.description == "Updated description"
    assert updated.entry_metadata["priority"] == "high"
    assert updated.updated_by == "editor-456"


@pytest.mark.asyncio
async def test_update_entry_status(copy_service: CopyService, sample_entry: CopyEntry):
    """Test updating entry status through lifecycle."""
    # Draft → Review
    await copy_service.update_entry(
        sample_entry.id, CopyEntryUpdate(status=CopyStatus.REVIEW)
    )
    entry = await copy_service.get_entry(sample_entry.id)
    assert entry.status == CopyStatus.REVIEW

    # Review → Approved
    await copy_service.update_entry(
        sample_entry.id, CopyEntryUpdate(status=CopyStatus.APPROVED)
    )
    entry = await copy_service.get_entry(sample_entry.id)
    assert entry.status == CopyStatus.APPROVED

    # Approved → Published
    await copy_service.update_entry(
        sample_entry.id, CopyEntryUpdate(status=CopyStatus.PUBLISHED)
    )
    entry = await copy_service.get_entry(sample_entry.id)
    assert entry.status == CopyStatus.PUBLISHED


# --- Test Variant Management ---


@pytest.mark.asyncio
async def test_add_variant_to_existing_entry(
    copy_service: CopyService, sample_entry: CopyEntry
):
    """Test adding new locale variant to existing entry."""
    variant_data = CopyVariantCreate(
        locale="fr",
        text="Signaux de Trading Professionnels",
        is_control=True,
    )

    variant = await copy_service.add_variant(sample_entry.id, variant_data)

    assert variant.id is not None
    assert variant.locale == "fr"
    assert variant.entry_id == sample_entry.id

    # Verify entry now has 3 variants
    await copy_service.db.refresh(sample_entry, attribute_names=["variants"])
    assert len(sample_entry.variants) == 3


@pytest.mark.asyncio
async def test_add_ab_test_variant(copy_service: CopyService, sample_entry: CopyEntry):
    """Test adding A/B test variant."""
    variant_data = CopyVariantCreate(
        locale="en",
        ab_group="variant_a",
        is_control=False,
        text="Trade Smarter with AI Signals",
    )

    variant = await copy_service.add_variant(sample_entry.id, variant_data)

    assert variant.ab_group == "variant_a"
    assert variant.is_control is False


# --- Test Copy Resolution ---


@pytest.mark.asyncio
async def test_resolve_copy_basic(
    copy_service: CopyService, sample_entry: CopyEntry, db_session: AsyncSession
):
    """Test basic copy resolution for published entries."""
    # Publish the entry
    await copy_service.update_entry(
        sample_entry.id, CopyEntryUpdate(status=CopyStatus.PUBLISHED)
    )
    await db_session.commit()

    # Resolve copy
    resolved, missing = await copy_service.resolve_copy(
        keys=["hero.title"], locale="en"
    )

    assert len(missing) == 0
    assert resolved["hero.title"] == "Professional Trading Signals"


@pytest.mark.asyncio
async def test_resolve_copy_locale_fallback(
    copy_service: CopyService, sample_entry: CopyEntry, db_session: AsyncSession
):
    """Test copy resolution with locale fallback."""
    await copy_service.update_entry(
        sample_entry.id, CopyEntryUpdate(status=CopyStatus.PUBLISHED)
    )
    await db_session.commit()

    # Request Spanish locale
    resolved, missing = await copy_service.resolve_copy(
        keys=["hero.title"], locale="es"
    )

    assert resolved["hero.title"] == "Señales de Trading Profesionales"


@pytest.mark.asyncio
async def test_resolve_copy_missing_locale_falls_back_to_english(
    copy_service: CopyService, sample_entry: CopyEntry, db_session: AsyncSession
):
    """Test fallback to English when requested locale not available."""
    await copy_service.update_entry(
        sample_entry.id, CopyEntryUpdate(status=CopyStatus.PUBLISHED)
    )
    await db_session.commit()

    # Request French (not available, should fall back to English)
    resolved, missing = await copy_service.resolve_copy(
        keys=["hero.title"], locale="fr"
    )

    assert resolved["hero.title"] == "Professional Trading Signals"  # English fallback


@pytest.mark.asyncio
async def test_resolve_copy_missing_keys_detected(
    copy_service: CopyService, db_session: AsyncSession
):
    """Test that missing keys are properly detected."""
    resolved, missing = await copy_service.resolve_copy(
        keys=["nonexistent.key", "another.missing.key"], locale="en"
    )

    assert len(resolved) == 0
    assert len(missing) == 2
    assert "nonexistent.key" in missing
    assert "another.missing.key" in missing


@pytest.mark.asyncio
async def test_resolve_copy_draft_entries_not_returned(
    copy_service: CopyService, sample_entry: CopyEntry, db_session: AsyncSession
):
    """Test that draft entries are not resolved (only published)."""
    # Entry is in DRAFT status by default
    assert sample_entry.status == CopyStatus.DRAFT

    # Try to resolve
    resolved, missing = await copy_service.resolve_copy(
        keys=["hero.title"], locale="en"
    )

    # Should not be returned (only published copy is resolved)
    assert len(resolved) == 0
    assert "hero.title" in missing


# --- Test A/B Testing Metrics ---


@pytest.mark.asyncio
async def test_ab_test_impression_tracking(
    copy_service: CopyService, sample_entry: CopyEntry, db_session: AsyncSession
):
    """Test impression tracking for A/B testing."""
    # Publish entry
    await copy_service.update_entry(
        sample_entry.id, CopyEntryUpdate(status=CopyStatus.PUBLISHED)
    )
    await db_session.commit()

    # Resolve with impression tracking
    resolved, _ = await copy_service.resolve_copy(
        keys=["hero.title"], locale="en", record_impression=True
    )

    # Verify impression recorded
    entry = await copy_service.get_entry(sample_entry.id)
    en_variant = entry.get_variant("en")
    assert en_variant.impressions == 1
    assert en_variant.conversions == 0
    assert en_variant.conversion_rate == 0.0


@pytest.mark.asyncio
async def test_ab_test_conversion_tracking(
    copy_service: CopyService, sample_entry: CopyEntry, db_session: AsyncSession
):
    """Test conversion tracking for A/B testing."""
    await copy_service.update_entry(
        sample_entry.id, CopyEntryUpdate(status=CopyStatus.PUBLISHED)
    )
    await db_session.commit()

    # Record impressions
    for _ in range(10):
        await copy_service.record_impression(key="hero.title", locale="en")

    # Record conversions
    for _ in range(3):
        await copy_service.record_conversion(key="hero.title", locale="en")

    # Verify metrics
    entry = await copy_service.get_entry(sample_entry.id)
    en_variant = entry.get_variant("en")
    assert en_variant.impressions == 10
    assert en_variant.conversions == 3
    assert en_variant.conversion_rate == pytest.approx(0.3)


@pytest.mark.asyncio
async def test_ab_test_variant_selection(
    copy_service: CopyService, sample_entry: CopyEntry, db_session: AsyncSession
):
    """Test A/B variant selection by ab_group."""
    # Add A/B test variant
    await copy_service.add_variant(
        sample_entry.id,
        CopyVariantCreate(
            locale="en",
            ab_group="variant_a",
            is_control=False,
            text="Trade Smarter with AI",
        ),
    )
    await copy_service.update_entry(
        sample_entry.id, CopyEntryUpdate(status=CopyStatus.PUBLISHED)
    )
    await db_session.commit()

    # Resolve for control group
    resolved_control, _ = await copy_service.resolve_copy(
        keys=["hero.title"], locale="en", ab_group=None
    )
    assert resolved_control["hero.title"] == "Professional Trading Signals"

    # Resolve for variant_a group
    resolved_variant, _ = await copy_service.resolve_copy(
        keys=["hero.title"], locale="en", ab_group="variant_a"
    )
    assert resolved_variant["hero.title"] == "Trade Smarter with AI"


# --- Test Listing & Filtering ---


@pytest.mark.asyncio
async def test_list_entries_with_type_filter(copy_service: CopyService):
    """Test listing entries filtered by type."""
    # Create entries of different types
    await copy_service.create_entry(
        CopyEntryCreate(
            key="product.button",
            type=CopyType.PRODUCT,
            variants=[CopyVariantCreate(locale="en", text="Click Me")],
        )
    )
    await copy_service.create_entry(
        CopyEntryCreate(
            key="marketing.cta",
            type=CopyType.MARKETING,
            variants=[CopyVariantCreate(locale="en", text="Sign Up Now")],
        )
    )

    # Filter by PRODUCT type
    product_entries = await copy_service.list_entries(type=CopyType.PRODUCT)
    assert len(product_entries) == 1
    assert product_entries[0].key == "product.button"

    # Filter by MARKETING type
    marketing_entries = await copy_service.list_entries(type=CopyType.MARKETING)
    assert len(marketing_entries) == 1
    assert marketing_entries[0].key == "marketing.cta"


@pytest.mark.asyncio
async def test_list_entries_with_status_filter(copy_service: CopyService):
    """Test listing entries filtered by status."""
    await copy_service.create_entry(
        CopyEntryCreate(
            key="draft.entry",
            type=CopyType.PRODUCT,
            variants=[CopyVariantCreate(locale="en", text="Draft")],
        )
    )
    entry2 = await copy_service.create_entry(
        CopyEntryCreate(
            key="published.entry",
            type=CopyType.PRODUCT,
            variants=[CopyVariantCreate(locale="en", text="Published")],
        )
    )

    # Publish entry2
    await copy_service.update_entry(
        entry2.id, CopyEntryUpdate(status=CopyStatus.PUBLISHED)
    )

    # Filter by DRAFT status
    draft_entries = await copy_service.list_entries(status=CopyStatus.DRAFT)
    assert len(draft_entries) == 1
    assert draft_entries[0].key == "draft.entry"

    # Filter by PUBLISHED status
    published_entries = await copy_service.list_entries(status=CopyStatus.PUBLISHED)
    assert len(published_entries) == 1
    assert published_entries[0].key == "published.entry"


# --- Test Deletion & Cascades ---


@pytest.mark.asyncio
async def test_delete_entry_cascades_to_variants(
    copy_service: CopyService, sample_entry: CopyEntry, db_session: AsyncSession
):
    """Test that deleting entry cascades to all variants."""
    entry_id = sample_entry.id
    variant_ids = [v.id for v in sample_entry.variants]

    # Delete entry
    deleted = await copy_service.delete_entry(entry_id)
    assert deleted is True

    # Verify entry deleted
    entry = await copy_service.get_entry(entry_id)
    assert entry is None

    # Verify variants deleted (cascade)
    for variant_id in variant_ids:
        result = await db_session.execute(
            select(CopyVariant).where(CopyVariant.id == variant_id)
        )
        variant = result.scalars().first()
        assert variant is None


@pytest.mark.asyncio
async def test_delete_nonexistent_entry(copy_service: CopyService):
    """Test deleting non-existent entry returns False."""
    deleted = await copy_service.delete_entry("nonexistent-id")
    assert deleted is False


# --- Test Model Properties ---


@pytest.mark.asyncio
async def test_copy_entry_default_variant_property(sample_entry: CopyEntry):
    """Test default_variant property returns English control."""
    default = sample_entry.default_variant
    assert default is not None
    assert default.locale == "en"
    assert default.is_control is True


@pytest.mark.asyncio
async def test_copy_entry_get_variant_method(sample_entry: CopyEntry):
    """Test get_variant method with locale."""
    en_variant = sample_entry.get_variant("en")
    assert en_variant.locale == "en"
    assert en_variant.text == "Professional Trading Signals"

    es_variant = sample_entry.get_variant("es")
    assert es_variant.locale == "es"
    assert es_variant.text == "Señales de Trading Profesionales"


@pytest.mark.asyncio
async def test_copy_variant_record_impression_updates_metrics(db_session: AsyncSession):
    """Test that recording impression updates metrics correctly."""
    # Create parent entry first
    entry = CopyEntry(
        id="test-entry",
        key="test.key",
        type=CopyType.MARKETING,
        description="Test Entry",
        status=CopyStatus.PUBLISHED,
    )
    db_session.add(entry)
    await db_session.commit()

    variant = CopyVariant(
        entry_id="test-entry",
        locale="en",
        text="Test",
        impressions=0,
        conversions=0,
    )
    db_session.add(variant)
    await db_session.commit()

    # Record impression
    variant.record_impression()
    assert variant.impressions == 1
    assert variant.conversion_rate == 0.0

    # Record conversion
    variant.record_conversion()
    assert variant.conversions == 1
    assert variant.conversion_rate == pytest.approx(1.0)

    # Record more impressions
    variant.record_impression()
    variant.record_impression()
    assert variant.impressions == 3
    assert variant.conversion_rate == pytest.approx(1.0 / 3.0)


# --- Test Edge Cases ---


@pytest.mark.asyncio
async def test_resolve_copy_multiple_keys_mixed_results(
    copy_service: CopyService, sample_entry: CopyEntry, db_session: AsyncSession
):
    """Test resolving multiple keys where some exist and some don't."""
    await copy_service.update_entry(
        sample_entry.id, CopyEntryUpdate(status=CopyStatus.PUBLISHED)
    )
    await db_session.commit()

    resolved, missing = await copy_service.resolve_copy(
        keys=["hero.title", "nonexistent.key", "another.missing"], locale="en"
    )

    assert len(resolved) == 1
    assert "hero.title" in resolved
    assert len(missing) == 2
    assert "nonexistent.key" in missing
    assert "another.missing" in missing


@pytest.mark.asyncio
async def test_resolve_copy_empty_keys_list(copy_service: CopyService):
    """Test resolving with empty keys list."""
    resolved, missing = await copy_service.resolve_copy(keys=[], locale="en")
    assert len(resolved) == 0
    assert len(missing) == 0


@pytest.mark.asyncio
async def test_record_impression_for_nonexistent_key(copy_service: CopyService):
    """Test recording impression for non-existent key returns False."""
    recorded = await copy_service.record_impression("nonexistent.key", "en")
    assert recorded is False


@pytest.mark.asyncio
async def test_record_conversion_for_nonexistent_key(copy_service: CopyService):
    """Test recording conversion for non-existent key returns False."""
    recorded = await copy_service.record_conversion("nonexistent.key", "en")
    assert recorded is False
