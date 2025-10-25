"""Storage backend for chart exports and media files."""

import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class StorageManager:
    """Manage storage of rendered charts and exports.

    Handles:
    - PNG/CSV file persistence
    - Directory organization by date/user
    - Cleanup of old files
    - Path management
    """

    def __init__(self, base_path: str = "media"):
        """Initialize storage manager.

        Args:
            base_path: Base directory for media storage
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Storage initialized: {self.base_path}")

    def save_chart(
        self,
        png_bytes: bytes,
        user_id: str,
        chart_name: str,
        chart_type: str = "candlestick",
    ) -> Path:
        """Save rendered chart to disk.

        Args:
            png_bytes: PNG image bytes
            user_id: User ID for organization
            chart_name: Descriptive chart name
            chart_type: Type of chart (candlestick, equity, etc.)

        Returns:
            Path to saved file

        File path pattern:
            media/YYYY-MM-DD/{user_id}/{chart_type}/{chart_name}.png
        """
        try:
            # Create directory structure
            today = datetime.utcnow().strftime("%Y-%m-%d")
            chart_dir = self.base_path / today / user_id / chart_type
            chart_dir.mkdir(parents=True, exist_ok=True)

            # Generate filename with timestamp
            timestamp = datetime.utcnow().strftime("%H%M%S")
            filename = f"{chart_name}_{timestamp}.png"
            file_path = chart_dir / filename

            # Write file
            with open(file_path, "wb") as f:
                f.write(png_bytes)

            logger.info(
                f"Chart saved: {file_path} ({len(png_bytes)} bytes, user_id={user_id})"
            )
            return file_path

        except Exception as e:
            logger.error(f"Failed to save chart: {e}", exc_info=True)
            raise

    def save_export(
        self,
        content: bytes,
        user_id: str,
        filename: str,
        file_type: str = "csv",
    ) -> Path:
        """Save export file (CSV, JSON, etc.).

        Args:
            content: File content as bytes
            user_id: User ID for organization
            filename: Descriptive filename (without extension)
            file_type: File extension (csv, json, etc.)

        Returns:
            Path to saved file
        """
        try:
            # Create directory structure
            today = datetime.utcnow().strftime("%Y-%m-%d")
            export_dir = self.base_path / today / user_id / "exports"
            export_dir.mkdir(parents=True, exist_ok=True)

            # Generate filename with timestamp
            timestamp = datetime.utcnow().strftime("%H%M%S")
            full_filename = f"{filename}_{timestamp}.{file_type}"
            file_path = export_dir / full_filename

            # Write file
            with open(file_path, "wb") as f:
                f.write(content)

            logger.info(
                f"Export saved: {file_path} ({len(content)} bytes, user_id={user_id})"
            )
            return file_path

        except Exception as e:
            logger.error(f"Failed to save export: {e}", exc_info=True)
            raise

    def get_file_url(self, file_path: Path) -> str:
        """Convert file path to CDN/web URL.

        Args:
            file_path: Path object returned from save_chart/save_export

        Returns:
            URL-safe path relative to base_path
        """
        try:
            relative_path = file_path.relative_to(self.base_path)
            # URL-safe path (forward slashes)
            url_path = str(relative_path).replace(os.sep, "/")
            return f"/media/{url_path}"
        except Exception as e:
            logger.error(f"Failed to generate URL: {e}")
            raise

    def cleanup_old_files(self, days_to_keep: int = 30) -> int:
        """Delete media files older than specified days.

        Args:
            days_to_keep: Keep files newer than this many days

        Returns:
            Number of files deleted
        """
        try:
            from datetime import timedelta

            cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
            deleted_count = 0

            for file_path in self.base_path.rglob("*"):
                if file_path.is_file():
                    mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if mtime < cutoff_date:
                        file_path.unlink()
                        deleted_count += 1
                        logger.debug(f"Deleted old file: {file_path}")

            logger.info(
                f"Cleanup: Deleted {deleted_count} files older than {days_to_keep} days"
            )
            return deleted_count

        except Exception as e:
            logger.error(f"Cleanup failed: {e}", exc_info=True)
            raise
