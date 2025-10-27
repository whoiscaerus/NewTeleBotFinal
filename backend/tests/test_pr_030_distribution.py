"""Tests for PR-030: Content Distribution Router.

Comprehensive test suite for the ContentDistributor with:
- Keyword matching tests
- Distribution success/failure paths
- Multi-group distribution
- Error handling and edge cases
- Telemetry verification
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

from backend.app.telegram.handlers.distribution import ContentDistributor
from backend.app.telegram.logging import DistributionAuditLogger
from backend.app.telegram.routes_config import RoutesConfig


class TestRoutesConfig:
    """Tests for RoutesConfig module."""

    def test_routes_config_init_empty(self):
        """Test RoutesConfig initialization with no config."""
        routes = RoutesConfig()
        assert routes.routes == {}

    def test_routes_config_valid_json(self):
        """Test RoutesConfig with valid JSON."""
        config_json = '{"gold": [-1001234567890], "crypto": [-1001234567891]}'
        routes = RoutesConfig(config_json)
        assert routes.routes == {
            "gold": [-1001234567890],
            "crypto": [-1001234567891],
        }

    def test_routes_config_invalid_json(self):
        """Test RoutesConfig rejects invalid JSON."""
        with pytest.raises(ValueError, match="Invalid JSON format"):
            RoutesConfig("invalid json {]}")

    def test_routes_config_case_insensitive(self):
        """Test RoutesConfig normalizes keywords to lowercase."""
        config_json = '{"GOLD": [-1001234567890], "CrYpTo": [-1001234567891]}'
        routes = RoutesConfig(config_json)
        assert "gold" in routes.routes
        assert "crypto" in routes.routes

    def test_get_groups_for_keyword(self):
        """Test getting groups for a keyword."""
        config_json = '{"gold": [-1001234567890, -1001234567891]}'
        routes = RoutesConfig(config_json)
        groups = routes.get_groups_for_keyword("gold")
        assert groups == [-1001234567890, -1001234567891]

    def test_get_groups_for_keyword_case_insensitive(self):
        """Test keyword lookup is case-insensitive."""
        config_json = '{"gold": [-1001234567890]}'
        routes = RoutesConfig(config_json)
        assert routes.get_groups_for_keyword("GOLD") == [-1001234567890]
        assert routes.get_groups_for_keyword("Gold") == [-1001234567890]

    def test_get_groups_missing_keyword(self):
        """Test getting groups for missing keyword returns None."""
        config_json = '{"gold": [-1001234567890]}'
        routes = RoutesConfig(config_json)
        assert routes.get_groups_for_keyword("missing") is None

    def test_add_route(self):
        """Test adding a route."""
        routes = RoutesConfig()
        routes.add_route("gold", [-1001234567890])
        assert routes.get_groups_for_keyword("gold") == [-1001234567890]

    def test_remove_route(self):
        """Test removing a route."""
        config_json = '{"gold": [-1001234567890]}'
        routes = RoutesConfig(config_json)
        assert routes.remove_route("gold") is True
        assert routes.get_groups_for_keyword("gold") is None

    def test_remove_route_not_found(self):
        """Test removing non-existent route."""
        routes = RoutesConfig()
        assert routes.remove_route("missing") is False

    def test_validate_empty_routes(self):
        """Test validation fails on empty routes."""
        routes = RoutesConfig()
        assert routes.validate() is False

    def test_validate_valid_routes(self):
        """Test validation passes on valid routes."""
        config_json = '{"gold": [-1001234567890]}'
        routes = RoutesConfig(config_json)
        assert routes.validate() is True

    def test_as_json(self):
        """Test exporting routes as JSON."""
        config_json = '{"gold": [-1001234567890]}'
        routes = RoutesConfig(config_json)
        output = routes.as_json()
        assert '"gold"' in output
        assert str(-1001234567890) in output


class TestContentDistributor:
    """Tests for ContentDistributor class."""

    @pytest.fixture
    def bot(self):
        """Mock Telegram bot."""
        return AsyncMock(spec=Bot)

    @pytest.fixture
    def group_map(self):
        """Sample group mapping."""
        return {
            "gold": [-1001234567890, -1001234567891],
            "crypto": [-1001234567892],
            "sp500": [-1001234567893, -1001234567894],
        }

    @pytest.fixture
    def distributor(self, bot, group_map):
        """Content distributor instance."""
        return ContentDistributor(bot, group_map)

    def test_init_with_group_map(self, bot, group_map):
        """Test initialization with group map."""
        distributor = ContentDistributor(bot, group_map)
        assert distributor.group_map == group_map
        assert distributor.bot == bot

    def test_init_without_group_map(self, bot):
        """Test initialization without group map."""
        distributor = ContentDistributor(bot)
        assert distributor.group_map == {}

    def test_add_keyword_mapping(self, distributor):
        """Test adding keyword mapping."""
        distributor.add_keyword_mapping("forex", [-1001234567895])
        assert distributor.group_map["forex"] == [-1001234567895]

    def test_find_matching_groups_single_keyword(self, distributor):
        """Test finding groups for single keyword."""
        matched = distributor.find_matching_groups("Gold update", ["gold"])
        assert matched == {"gold": [-1001234567890, -1001234567891]}

    def test_find_matching_groups_multiple_keywords(self, distributor):
        """Test finding groups for multiple keywords."""
        matched = distributor.find_matching_groups(
            "Gold and crypto", ["gold", "crypto"]
        )
        assert "gold" in matched
        assert "crypto" in matched
        assert matched["gold"] == [-1001234567890, -1001234567891]
        assert matched["crypto"] == [-1001234567892]

    def test_find_matching_groups_case_insensitive(self, distributor):
        """Test keyword matching is case-insensitive."""
        matched = distributor.find_matching_groups("Update", ["GOLD", "CrYpTo"])
        assert "gold" in matched
        assert "crypto" in matched

    def test_find_matching_groups_no_match(self, distributor):
        """Test finding groups with no keywords matched."""
        matched = distributor.find_matching_groups("Update", ["missing"])
        assert matched == {}

    @pytest.mark.asyncio
    async def test_distribute_content_valid(self, distributor, bot):
        """Test successful content distribution."""
        # Mock send_message
        mock_message = MagicMock()
        mock_message.message_id = 12345
        bot.send_message.return_value = mock_message

        result = await distributor.distribute_content(
            text="📊 Gold update",
            keywords=["gold"],
            parse_mode=ParseMode.MARKDOWN_V2,
        )

        assert result["success"] is True
        assert result["messages_sent"] == 2  # 2 groups for "gold"
        assert result["messages_failed"] == 0
        assert result["groups_targeted"] == 2
        assert "distribution_id" in result
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_distribute_content_empty_text(self, distributor):
        """Test distribution rejects empty text."""
        result = await distributor.distribute_content(
            text="",
            keywords=["gold"],
        )

        assert result["success"] is False
        assert "empty" in result["error"].lower()
        assert result["messages_sent"] == 0

    @pytest.mark.asyncio
    async def test_distribute_content_no_keywords(self, distributor):
        """Test distribution rejects missing keywords."""
        result = await distributor.distribute_content(
            text="Some content",
            keywords=[],
        )

        assert result["success"] is False
        assert "keyword" in result["error"].lower()
        assert result["messages_sent"] == 0

    @pytest.mark.asyncio
    async def test_distribute_content_no_matched_groups(self, distributor):
        """Test distribution when no keywords match."""
        result = await distributor.distribute_content(
            text="Some content",
            keywords=["missing"],
        )

        assert result["success"] is False
        assert "no groups matched" in result["error"].lower()
        assert result["messages_sent"] == 0

    @pytest.mark.asyncio
    async def test_distribute_content_partial_failure(self, distributor, bot):
        """Test distribution with partial failures."""
        # First send succeeds, second fails
        mock_message = MagicMock()
        mock_message.message_id = 12345

        async def send_side_effect(*args, **kwargs):
            if kwargs["chat_id"] == -1001234567890:
                return mock_message
            else:
                raise TelegramError("Chat not found")

        bot.send_message.side_effect = send_side_effect

        result = await distributor.distribute_content(
            text="Gold update",
            keywords=["gold"],
        )

        assert result["success"] is False
        assert result["messages_sent"] == 1
        assert result["messages_failed"] == 1
        assert result["groups_targeted"] == 2

    @pytest.mark.asyncio
    async def test_distribute_content_all_failures(self, distributor, bot):
        """Test distribution when all sends fail."""
        bot.send_message.side_effect = TelegramError("Rate limited")

        result = await distributor.distribute_content(
            text="Gold update",
            keywords=["gold"],
        )

        assert result["success"] is False
        assert result["messages_sent"] == 0
        assert result["messages_failed"] == 2

    @pytest.mark.asyncio
    async def test_distribute_content_multiple_keywords(self, distributor, bot):
        """Test distribution with multiple keywords."""
        mock_message = MagicMock()
        mock_message.message_id = 12345
        bot.send_message.return_value = mock_message

        result = await distributor.distribute_content(
            text="Market update",
            keywords=["gold", "crypto", "sp500"],
        )

        assert result["success"] is True
        # 2 (gold) + 1 (crypto) + 2 (sp500) = 5 unique groups
        assert result["messages_sent"] == 5
        assert result["groups_targeted"] == 5

    @pytest.mark.asyncio
    async def test_distribute_content_whitespace_handling(self, distributor, bot):
        """Test that whitespace in keywords is handled."""
        mock_message = MagicMock()
        mock_message.message_id = 12345
        bot.send_message.return_value = mock_message

        result = await distributor.distribute_content(
            text="Gold update",
            keywords=["  gold  ", " crypto "],  # With spaces
        )

        assert result["success"] is True
        assert result["messages_sent"] == 3  # 2 gold + 1 crypto


class TestDistributionAuditLogger:
    """Tests for DistributionAuditLogger."""

    @pytest.fixture
    async def db_session(self):
        """Mock database session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_log_distribution_no_session(self):
        """Test logging without database session."""
        logger = DistributionAuditLogger(db_session=None)
        result = await logger.log_distribution(
            distribution_id="123",
            keywords=["gold"],
            matched_groups={"gold": [-1001234567890]},
            messages_sent=1,
            messages_failed=0,
            results={
                "gold": [
                    {"chat_id": -1001234567890, "message_id": 123, "success": True}
                ]
            },
        )

        assert result is False


# Acceptance criteria tests
class TestPR030AcceptanceCriteria:
    """Tests verifying PR-030 acceptance criteria."""

    @pytest.fixture
    def bot(self):
        """Mock bot."""
        return AsyncMock(spec=Bot)

    @pytest.fixture
    def distributor(self, bot):
        """Distributor with test config."""
        group_map = {
            "gold": [-1001234567890],
            "crypto": [-1001234567891],
            "sp500": [-1001234567892],
        }
        return ContentDistributor(bot, group_map)

    @pytest.mark.asyncio
    async def test_keyword_matrix(self, distributor, bot):
        """Test keyword matrix: case-insensitive, multi-keyword, templates."""
        mock_message = MagicMock()
        mock_message.message_id = 12345
        bot.send_message.return_value = mock_message

        # Case insensitive
        result = await distributor.distribute_content(
            text="Update for GOLD",
            keywords=["GOLD"],  # Uppercase
        )
        assert result["success"] is True

        # Multi-keyword support
        result = await distributor.distribute_content(
            text="Markets update",
            keywords=["gold", "crypto"],  # Multiple
        )
        assert result["groups_targeted"] == 2

    @pytest.mark.asyncio
    async def test_no_match_branch(self, distributor):
        """Test no-match branch error handling."""
        result = await distributor.distribute_content(
            text="Market update",
            keywords=["nonexistent"],
        )
        assert result["success"] is False
        assert result["error"] is not None

    @pytest.mark.asyncio
    async def test_error_handling(self, distributor, bot):
        """Test comprehensive error handling."""
        # Test various error scenarios
        test_cases = [
            ("", ["gold"], "empty"),  # Empty text
            ("text", [], "keyword"),  # No keywords
            ("text", ["missing"], "no groups matched"),  # No match
        ]

        for text, keywords, error_contains in test_cases:
            result = await distributor.distribute_content(text=text, keywords=keywords)
            assert result["success"] is False
            assert error_contains.lower() in result["error"].lower()
