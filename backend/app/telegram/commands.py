"""Telegram command registry with role-based access control."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class UserRole(str, Enum):
    """User role levels for command access control."""

    PUBLIC = "public"  # Available to all users
    SUBSCRIBER = "subscriber"  # Paid subscribers only
    OWNER = "owner"  # Bot owner/admin
    ADMIN = "admin"  # Admin users


@dataclass
class CommandInfo:
    """Information about a Telegram command.

    Attributes:
        name: Command name (e.g., "start", "help", "shop")
        description: Short description of what command does
        required_role: Minimum role required to execute
        handler: Async callable to execute command
        help_text: Full help text for /help command
        aliases: Alternative names for command
        hidden: If True, don't show in /help menu
    """

    name: str
    description: str
    required_role: UserRole
    handler: Callable
    help_text: str
    aliases: list[str] = None
    hidden: bool = False

    def __post_init__(self):
        """Validate command info."""
        if self.aliases is None:
            self.aliases = []

        if not self.name:
            raise ValueError("Command name required")
        if not callable(self.handler):
            raise ValueError(f"Handler for {self.name} must be callable")


class CommandRegistry:
    """Registry of Telegram commands with role-based access control.

    Maps command names to handlers and enforces role requirements.
    Provides command discovery and validation.

    Example:
        >>> registry = CommandRegistry()
        >>> registry.register(
        ...     name="admin",
        ...     description="Admin commands",
        ...     required_role=UserRole.ADMIN,
        ...     handler=handle_admin,
        ...     help_text="Admin-only commands..."
        ... )
        >>> is_allowed = registry.is_allowed("admin", UserRole.SUBSCRIBER)
        >>> assert is_allowed is False  # Subscriber can't access admin
    """

    def __init__(self):
        """Initialize command registry."""
        self.commands: dict[str, CommandInfo] = {}
        self._alias_map: dict[str, str] = {}  # Maps aliases to canonical command names

    def register(
        self,
        name: str,
        description: str,
        required_role: UserRole,
        handler: Callable,
        help_text: str,
        aliases: list[str] = None,
        hidden: bool = False,
    ) -> None:
        """Register a command.

        Args:
            name: Command name (canonical)
            description: Short description
            required_role: Required UserRole to execute
            handler: Async function to handle command
            help_text: Full help text for /help
            aliases: Alternative command names
            hidden: If True, don't show in /help

        Raises:
            ValueError: If command already registered or parameters invalid

        Example:
            >>> registry.register(
            ...     name="shop",
            ...     description="Browse products",
            ...     required_role=UserRole.PUBLIC,
            ...     handler=handle_shop,
            ...     help_text="View our product catalog..."
            ... )
        """
        if name in self.commands:
            raise ValueError(f"Command '{name}' already registered")

        # Validate handler is async
        import inspect

        if not inspect.iscoroutinefunction(handler):
            raise ValueError(f"Handler for '{name}' must be async")

        # Create command info
        command_info = CommandInfo(
            name=name,
            description=description,
            required_role=required_role,
            handler=handler,
            help_text=help_text,
            aliases=aliases or [],
            hidden=hidden,
        )

        # Register command
        self.commands[name] = command_info

        # Register aliases
        for alias in command_info.aliases:
            if alias in self._alias_map:
                raise ValueError(f"Alias '{alias}' already mapped to command")
            self._alias_map[alias] = name

        logger.debug(
            f"Command registered: {name}",
            extra={"role": required_role, "aliases": len(command_info.aliases)},
        )

    def get_command(self, name: str) -> CommandInfo | None:
        """Get command by name or alias.

        Args:
            name: Command name or alias

        Returns:
            CommandInfo or None if not found

        Example:
            >>> cmd = registry.get_command("shop")
            >>> assert cmd.description == "Browse products"
        """
        # Check if it's a direct command
        if name in self.commands:
            return self.commands[name]

        # Check if it's an alias
        canonical_name = self._alias_map.get(name)
        if canonical_name:
            return self.commands[canonical_name]

        return None

    def is_registered(self, name: str) -> bool:
        """Check if command is registered.

        Args:
            name: Command name or alias

        Returns:
            True if command exists
        """
        return name in self.commands or name in self._alias_map

    def is_allowed(self, command_name: str, user_role: UserRole) -> bool:
        """Check if user role can execute command.

        Args:
            command_name: Command name
            user_role: User's role

        Returns:
            True if user's role >= command's required_role

        Roles hierarchy (highest to lowest):
            - OWNER: Highest privileges
            - ADMIN: Admin privileges
            - SUBSCRIBER: Paid subscriber
            - PUBLIC: Any user

        Example:
            >>> registry.is_allowed("admin_broadcast", UserRole.SUBSCRIBER)
            False  # Only admin can access
        """
        command_info = self.get_command(command_name)
        if not command_info:
            return False

        # Role hierarchy for comparison
        role_hierarchy = {
            UserRole.OWNER: 4,
            UserRole.ADMIN: 3,
            UserRole.SUBSCRIBER: 2,
            UserRole.PUBLIC: 1,
        }

        required_level = role_hierarchy.get(command_info.required_role, 0)
        user_level = role_hierarchy.get(user_role, 0)

        allowed = user_level >= required_level
        logger.debug(
            f"Permission check: command={command_name}, user_role={user_role}, allowed={allowed}"
        )

        return allowed

    def get_all_commands(self) -> list[CommandInfo]:
        """Get all registered commands.

        Returns:
            List of all CommandInfo objects
        """
        return list(self.commands.values())

    def get_public_commands(self) -> list[CommandInfo]:
        """Get commands available to public users.

        Returns:
            List of PUBLIC-role commands
        """
        return [
            cmd
            for cmd in self.commands.values()
            if cmd.required_role == UserRole.PUBLIC
        ]

    def get_help_text(self, user_role: UserRole) -> str:
        """Generate help text for user's role level.

        Only includes commands user is allowed to execute.

        Args:
            user_role: User's role

        Returns:
            Formatted help text with available commands

        Example:
            >>> help = registry.get_help_text(UserRole.PUBLIC)
            >>> assert "/start" in help
            >>> assert "/admin" not in help  # Public can't see admin commands
        """
        available_commands = [
            cmd
            for cmd in self.commands.values()
            if not cmd.hidden and self.is_allowed(cmd.name, user_role)
        ]

        if not available_commands:
            return "No commands available for your role."

        help_lines = ["📖 *Available Commands*\n"]

        for cmd in sorted(available_commands, key=lambda c: c.name):
            help_lines.append(f"• /{cmd.name} - {cmd.description}")

        help_lines.append("\n_Type /help [command] for more details_")

        return "\n".join(help_lines)

    def get_command_help(self, command_name: str) -> str | None:
        """Get detailed help for specific command.

        Args:
            command_name: Command name

        Returns:
            Full help text or None if command not found
        """
        command_info = self.get_command(command_name)
        if not command_info:
            return None

        help_text = f"*/{command_info.name}*\n\n{command_info.help_text}"

        if command_info.aliases:
            help_text += f"\n\n_Aliases: {', '.join(command_info.aliases)}_"

        return help_text

    def list_commands_for_role(self, user_role: UserRole) -> list[str]:
        """List command names available for role.

        Args:
            user_role: User's role

        Returns:
            List of command names user can execute
        """
        return [
            cmd.name
            for cmd in self.commands.values()
            if self.is_allowed(cmd.name, user_role)
        ]


# Global registry instance
_global_registry: CommandRegistry | None = None


def get_registry() -> CommandRegistry:
    """Get or create global command registry.

    Returns:
        Global CommandRegistry instance
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = CommandRegistry()
    return _global_registry


def reset_registry() -> None:
    """Reset global registry (useful for testing).

    This clears all registered commands and resets to empty state.
    """
    global _global_registry
    _global_registry = None
