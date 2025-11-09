"""Strategy registry for pluggable trading strategy engines.

Provides registration and discovery of strategy engines (Fib/RSI, PPO, future variants).
Strategies are loaded from STRATEGIES_ENABLED environment variable.

Flow:
    1. Register strategies with register_strategy(name, factory_fn)
    2. Initialize enabled strategies from env: STRATEGIES_ENABLED=fib_rsi,ppo_gold
    3. Scheduler queries enabled strategies and executes them on new candles
    4. Each strategy returns SignalCandidate objects

Example:
    >>> from backend.app.strategy.registry import StrategyRegistry
    >>> from backend.app.strategy.fib_rsi.engine import StrategyEngine
    >>>
    >>> registry = StrategyRegistry()
    >>> registry.register_strategy("fib_rsi", create_fib_rsi_strategy)
    >>> registry.register_strategy("ppo_gold", create_ppo_strategy)
    >>>
    >>> # Initialize enabled strategies
    >>> registry.initialize_enabled_strategies()
    >>>
    >>> # Get strategy instance
    >>> strategy = registry.get_strategy("fib_rsi")
    >>> signals = await strategy.generate_signal(df, "GOLD", datetime.utcnow())
"""

import logging
import os
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class StrategyRegistry:
    """Registry for trading strategy engines.

    Manages registration, initialization, and discovery of strategy engines.
    Strategies are factories that create strategy instances on demand.

    Attributes:
        _factories: Dict mapping strategy names to factory functions
        _instances: Dict of initialized strategy instances
        _enabled_strategies: Set of strategy names enabled via env
    """

    def __init__(self):
        """Initialize empty strategy registry."""
        self._factories: dict[str, Callable[[], Any]] = {}
        self._instances: dict[str, Any] = {}
        self._enabled_strategies: set[str] = set()

        logger.info("StrategyRegistry initialized")

    def register_strategy(
        self, name: str, factory: Callable[[], Any], description: str | None = None
    ) -> None:
        """Register a strategy factory.

        Args:
            name: Strategy name (e.g., "fib_rsi", "ppo_gold")
            factory: Factory function that creates strategy instance
            description: Optional human-readable description

        Raises:
            ValueError: If strategy name already registered

        Example:
            >>> registry = StrategyRegistry()
            >>> def create_fib_rsi():
            ...     from backend.app.strategy.fib_rsi.engine import StrategyEngine
            ...     from backend.app.strategy.fib_rsi.params import StrategyParams
            ...     from backend.app.trading.time import MarketCalendar
            ...     params = StrategyParams()
            ...     calendar = MarketCalendar()
            ...     return StrategyEngine(params, calendar)
            >>> registry.register_strategy("fib_rsi", create_fib_rsi)
        """
        if name in self._factories:
            raise ValueError(f"Strategy '{name}' already registered")

        self._factories[name] = factory

        logger.info(
            f"Registered strategy: {name}",
            extra={
                "strategy_name": name,
                "description": description or "No description",
            },
        )

    def get_strategy(self, name: str) -> Any:
        """Get initialized strategy instance by name.

        Returns cached instance if available, otherwise creates new instance.

        Args:
            name: Strategy name

        Returns:
            Strategy engine instance

        Raises:
            KeyError: If strategy not registered
            RuntimeError: If strategy factory fails

        Example:
            >>> registry = StrategyRegistry()
            >>> registry.register_strategy("fib_rsi", create_fib_rsi)
            >>> strategy = registry.get_strategy("fib_rsi")
        """
        if name not in self._factories:
            raise KeyError(f"Strategy '{name}' not registered")

        # Return cached instance if available
        if name in self._instances:
            logger.debug(f"Returning cached strategy instance: {name}")
            return self._instances[name]

        # Create new instance
        try:
            logger.info(f"Creating new strategy instance: {name}")
            factory = self._factories[name]
            instance = factory()
            self._instances[name] = instance
            return instance
        except Exception as e:
            logger.error(
                f"Failed to create strategy instance: {name}",
                exc_info=True,
                extra={"strategy_name": name, "error": str(e)},
            )
            raise RuntimeError(f"Failed to create strategy '{name}': {e}") from e

    def initialize_enabled_strategies(
        self, env_var: str = "STRATEGIES_ENABLED"
    ) -> list[str]:
        """Initialize strategies enabled via environment variable.

        Reads STRATEGIES_ENABLED env var (comma-separated list) and initializes
        each strategy. Caches instances for later use.

        Args:
            env_var: Environment variable name (default: STRATEGIES_ENABLED)

        Returns:
            List of successfully initialized strategy names

        Example:
            >>> os.environ["STRATEGIES_ENABLED"] = "fib_rsi,ppo_gold"
            >>> registry = StrategyRegistry()
            >>> # ... register strategies ...
            >>> enabled = registry.initialize_enabled_strategies()
            >>> print(enabled)  # ["fib_rsi", "ppo_gold"]
        """
        enabled_str = os.getenv(env_var, "")

        if not enabled_str:
            logger.warning(
                f"No strategies enabled. Set {env_var} environment variable.",
                extra={"env_var": env_var},
            )
            return []

        # Parse comma-separated list
        strategy_names = [
            name.strip() for name in enabled_str.split(",") if name.strip()
        ]

        if not strategy_names:
            logger.warning(
                f"{env_var} is empty or invalid",
                extra={"env_var": env_var, "value": enabled_str},
            )
            return []

        logger.info(
            f"Initializing enabled strategies: {strategy_names}",
            extra={"strategy_count": len(strategy_names), "strategies": strategy_names},
        )

        initialized = []

        for name in strategy_names:
            try:
                # Initialize strategy (creates instance and caches it)
                strategy = self.get_strategy(name)

                self._enabled_strategies.add(name)
                initialized.append(name)

                logger.info(
                    f"Successfully initialized strategy: {name}",
                    extra={
                        "strategy_name": name,
                        "strategy_type": type(strategy).__name__,
                    },
                )

            except Exception as e:
                logger.error(
                    f"Failed to initialize strategy: {name}",
                    exc_info=True,
                    extra={"strategy_name": name, "error": str(e)},
                )
                # Continue with other strategies instead of failing completely

        if not initialized:
            logger.error(
                f"Failed to initialize any strategies from {env_var}={enabled_str}",
                extra={"attempted": strategy_names, "env_var": env_var},
            )

        return initialized

    def get_enabled_strategies(self) -> list[str]:
        """Get list of enabled strategy names.

        Returns:
            List of enabled strategy names

        Example:
            >>> registry = StrategyRegistry()
            >>> registry.initialize_enabled_strategies()
            >>> enabled = registry.get_enabled_strategies()
        """
        return list(self._enabled_strategies)

    def get_all_registered(self) -> list[str]:
        """Get list of all registered strategy names (enabled or not).

        Returns:
            List of registered strategy names

        Example:
            >>> registry = StrategyRegistry()
            >>> registry.register_strategy("fib_rsi", create_fib_rsi)
            >>> registry.register_strategy("ppo_gold", create_ppo)
            >>> all_strategies = registry.get_all_registered()
            >>> print(all_strategies)  # ["fib_rsi", "ppo_gold"]
        """
        return list(self._factories.keys())

    def is_enabled(self, name: str) -> bool:
        """Check if strategy is enabled.

        Args:
            name: Strategy name

        Returns:
            True if strategy is enabled, False otherwise

        Example:
            >>> registry = StrategyRegistry()
            >>> os.environ["STRATEGIES_ENABLED"] = "fib_rsi"
            >>> registry.initialize_enabled_strategies()
            >>> registry.is_enabled("fib_rsi")  # True
            >>> registry.is_enabled("ppo_gold")  # False
        """
        return name in self._enabled_strategies

    def clear_cache(self) -> None:
        """Clear cached strategy instances.

        Useful for testing or forcing strategy re-initialization.

        Example:
            >>> registry = StrategyRegistry()
            >>> strategy1 = registry.get_strategy("fib_rsi")
            >>> registry.clear_cache()
            >>> strategy2 = registry.get_strategy("fib_rsi")
            >>> # strategy2 is a new instance
        """
        self._instances.clear()
        logger.info("Cleared strategy instance cache")


# Global registry instance
_registry: StrategyRegistry | None = None


def get_registry() -> StrategyRegistry:
    """Get or create global strategy registry.

    Returns:
        StrategyRegistry: Global instance

    Example:
        >>> from backend.app.strategy.registry import get_registry
        >>> registry = get_registry()
    """
    global _registry
    if _registry is None:
        _registry = StrategyRegistry()
    return _registry


def get_strategy(name: str) -> Any:
    """Helper to get strategy from global registry.

    Args:
        name: Strategy name

    Returns:
        Strategy instance

    Raises:
        KeyError: If strategy not registered

    Example:
        >>> from backend.app.strategy.registry import get_strategy
        >>> strategy = get_strategy("fib_rsi")
    """
    registry = get_registry()
    return registry.get_strategy(name)
