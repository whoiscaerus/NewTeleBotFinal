"""Configuration for content distribution routes (keywords to Telegram groups).

This module loads and manages the keyword-to-group mappings for content distribution.
It reads from TELEGRAM_GROUP_MAP_JSON environment variable and validates the structure.

Format of TELEGRAM_GROUP_MAP_JSON env var:
{
    "gold": [-1001234567890, -1001234567891],
    "crypto": [-1001234567892],
    "sp500": [-1001234567893, -1001234567894, -1001234567895],
    "forex": [-1001234567896]
}
"""

import json
import logging

logger = logging.getLogger(__name__)


class RoutesConfig:
    """Manages keyword-to-group route configuration."""

    def __init__(self, config_json: str | None = None):
        """Initialize routes configuration.

        Args:
            config_json: JSON string with keyword->group_ids mapping.
                        If None, will attempt to load from environment.

        Example:
            >>> config_json = '{"gold": [-1001234567890], "crypto": [-1001234567891]}'
            >>> routes = RoutesConfig(config_json)
            >>> groups = routes.get_groups_for_keyword("gold")
            >>> print(groups)  # [-1001234567890]
        """
        self.config_json = config_json
        self.routes: dict[str, list[int]] = {}
        self._load_routes()

    def _load_routes(self) -> None:
        """Load routes from config JSON.

        The JSON structure should be:
        {
            "keyword": [chat_id1, chat_id2, ...],
            ...
        }

        Raises:
            ValueError: If JSON is invalid or malformed.
            KeyError: If required fields are missing.
        """
        if not self.config_json:
            logger.warning("No routes configuration provided; using empty routes")
            self.routes = {}
            return

        try:
            parsed = json.loads(self.config_json)

            if not isinstance(parsed, dict):
                raise ValueError("Routes configuration must be a JSON object")

            # Validate each entry
            for keyword, group_ids in parsed.items():
                if not isinstance(keyword, str):
                    raise ValueError(f"Keyword must be string, got {type(keyword)}")

                if not isinstance(group_ids, list):
                    raise ValueError(
                        f"Group IDs for '{keyword}' must be a list, got {type(group_ids)}"
                    )

                if not group_ids:
                    logger.warning(f"Keyword '{keyword}' has no groups configured")
                    continue

                # Validate each group ID is an integer
                for group_id in group_ids:
                    if not isinstance(group_id, int):
                        raise ValueError(
                            f"Group ID for '{keyword}' must be integer, got {type(group_id)}"
                        )

                self.routes[keyword.lower().strip()] = group_ids

            logger.info(
                "Routes configuration loaded",
                extra={
                    "keyword_count": len(self.routes),
                    "total_groups": sum(len(v) for v in self.routes.values()),
                },
            )

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse routes JSON: {e}")
            raise ValueError(f"Invalid JSON format: {e}") from e

    def get_groups_for_keyword(self, keyword: str) -> list[int] | None:
        """Get group IDs for a keyword.

        Args:
            keyword: The keyword (case-insensitive).

        Returns:
            List of group chat IDs, or None if not found.

        Example:
            >>> routes = RoutesConfig(config_json)
            >>> groups = routes.get_groups_for_keyword("gold")
            >>> print(groups)  # [-1001234567890]
        """
        keyword_lower = keyword.lower().strip()
        return self.routes.get(keyword_lower)

    def add_route(self, keyword: str, group_ids: list[int]) -> None:
        """Add or update a route.

        Args:
            keyword: The keyword (case-insensitive).
            group_ids: List of group chat IDs.

        Example:
            >>> routes = RoutesConfig()
            >>> routes.add_route("gold", [-1001234567890])
        """
        keyword_lower = keyword.lower().strip()
        self.routes[keyword_lower] = group_ids
        logger.info(
            "Route added/updated",
            extra={"keyword": keyword_lower, "group_count": len(group_ids)},
        )

    def remove_route(self, keyword: str) -> bool:
        """Remove a route.

        Args:
            keyword: The keyword (case-insensitive).

        Returns:
            True if removed, False if not found.

        Example:
            >>> routes = RoutesConfig(config_json)
            >>> removed = routes.remove_route("gold")
            >>> print(removed)  # True
        """
        keyword_lower = keyword.lower().strip()
        if keyword_lower in self.routes:
            del self.routes[keyword_lower]
            logger.info("Route removed", extra={"keyword": keyword_lower})
            return True
        return False

    def get_all_routes(self) -> dict[str, list[int]]:
        """Get all configured routes.

        Returns:
            Dictionary of all keyword->groups mappings.

        Example:
            >>> routes = RoutesConfig(config_json)
            >>> all_routes = routes.get_all_routes()
            >>> print(all_routes)
        """
        return self.routes.copy()

    def validate(self) -> bool:
        """Validate routes configuration.

        Returns:
            True if valid, False otherwise.
        """
        if not self.routes:
            logger.warning("Routes configuration is empty")
            return False

        for keyword, group_ids in self.routes.items():
            if not keyword or not group_ids:
                logger.error(f"Invalid route: keyword='{keyword}', groups={group_ids}")
                return False

        return True

    def as_dict(self) -> dict[str, list[int]]:
        """Export routes as dictionary.

        Returns:
            Dictionary representation of routes.
        """
        return self.routes.copy()

    def as_json(self) -> str:
        """Export routes as JSON string.

        Returns:
            JSON representation of routes.
        """
        return json.dumps(self.routes, indent=2)
