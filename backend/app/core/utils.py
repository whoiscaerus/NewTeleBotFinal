"""
Utility functions for common operations across the application.

Includes:
- Text manipulation (slugification)
- String validation
- Format conversions
"""

import re
import unicodedata


def slugify(text: str) -> str:
    """
    Convert text to URL-safe slug format.

    Args:
        text: Text to convert to slug

    Returns:
        URL-safe slug (lowercase, hyphens instead of spaces, no special chars)

    Example:
        >>> slugify("Getting Started Guide!")
        'getting-started-guide'
        >>> slugify("Café au Lait")
        'cafe-au-lait'
    """
    # Normalize unicode characters (ü -> u, é -> e, etc.)
    text = unicodedata.normalize("NFD", text)
    text = text.encode("ascii", "ignore").decode("ascii")

    # Convert to lowercase
    text = text.lower()

    # Replace spaces and underscores with hyphens
    text = re.sub(r"[\s_]+", "-", text)

    # Remove any non-alphanumeric characters except hyphens
    text = re.sub(r"[^a-z0-9-]", "", text)

    # Remove multiple consecutive hyphens
    text = re.sub(r"-+", "-", text)

    # Strip hyphens from start and end
    text = text.strip("-")

    return text


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Truncate text to maximum length, adding suffix if needed.

    Args:
        text: Text to truncate
        max_length: Maximum length (including suffix)
        suffix: Text to append if truncated

    Returns:
        Truncated text with suffix if needed

    Example:
        >>> truncate_text("This is a long text", max_length=10)
        'This is...'
    """
    if len(text) <= max_length:
        return text

    return text[: max_length - len(suffix)] + suffix


def validate_email(email: str) -> bool:
    """
    Basic email validation.

    Args:
        email: Email address to validate

    Returns:
        True if email format is valid

    Example:
        >>> validate_email("user@example.com")
        True
        >>> validate_email("invalid")
        False
    """
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to remove unsafe characters.

    Args:
        filename: Original filename

    Returns:
        Sanitized filename safe for filesystem

    Example:
        >>> sanitize_filename("my file (1) [draft].pdf")
        'my_file_1_draft.pdf'
    """
    # Remove directory traversal attempts
    filename = filename.replace("..", "").replace("/", "").replace("\\", "")

    # Replace unsafe characters with underscores
    filename = re.sub(r"[^a-zA-Z0-9._-]", "_", filename)

    # Remove multiple consecutive underscores
    filename = re.sub(r"_+", "_", filename)

    return filename
