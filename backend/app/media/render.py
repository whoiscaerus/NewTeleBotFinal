"""Chart rendering with matplotlib backend and caching."""

import io
import logging
from typing import cast

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from PIL import Image

from backend.app.core.cache import CacheManager

logger = logging.getLogger(__name__)


class ChartRenderer:
    """Render trading charts with matplotlib backend and caching.

    Handles:
    - Candlestick charts with technical indicators
    - Equity curves with drawdown visualization
    - Performance metrics
    - PNG export with metadata stripping
    - LRU caching to reduce re-renders
    """

    def __init__(self, cache_manager: CacheManager, cache_ttl: int = 3600):
        """Initialize chart renderer.

        Args:
            cache_manager: Cache backend for rendered images
            cache_ttl: Cache TTL in seconds (default: 1 hour)
        """
        self.cache = cache_manager
        self.cache_ttl = cache_ttl
        # Set non-interactive backend to avoid GUI requirements
        plt.switch_backend("Agg")

    def render_candlestick(
        self,
        data: pd.DataFrame,
        title: str = "Price Chart",
        width: int = 1200,
        height: int = 600,
        show_sma: list[int] | None = None,
    ) -> bytes:
        """Render candlestick chart with optional moving averages.

        Args:
            data: DataFrame with OHLC + timestamp columns
            title: Chart title
            width: Chart width in pixels
            height: Chart height in pixels
            show_sma: List of SMA periods to display (e.g., [20, 50, 200])

        Returns:
            PNG bytes (metadata stripped)

        Expected DataFrame columns:
            - open, high, low, close: Price data
            - timestamp: Datetime index
        """
        # Generate cache key
        cache_key = self._gen_cache_key(f"candlestick_{title}_{len(data)}")

        # Check cache first
        cached_img = self.cache.get(cache_key)
        if cached_img is not None:
            logger.debug(f"Cache hit: {cache_key}")
            return cast(bytes, cached_img)

        logger.debug(f"Rendering candlestick chart: {title} ({len(data)} candles)")

        try:
            # Create figure
            fig, ax = plt.subplots(figsize=(width / 100, height / 100), dpi=100)

            # Extract OHLC data
            data = data.copy()
            data.index = pd.to_datetime(data["timestamp"])
            opens = data["open"]
            highs = data["high"]
            lows = data["low"]
            closes = data["close"]

            # Plot candlesticks
            for idx, (_, open_, high, low, close) in enumerate(
                zip(data.index, opens, highs, lows, closes, strict=True)
            ):
                color = "green" if close >= open_ else "red"
                # Wick
                ax.plot([idx, idx], [low, high], color=color, linewidth=1)
                # Body
                ax.bar(
                    idx,
                    abs(close - open_),
                    bottom=min(open_, close),
                    color=color,
                    width=0.6,
                )

            # Add moving averages if requested
            if show_sma:
                colors_sma = ["blue", "orange", "purple"]
                for period, color in zip(show_sma, colors_sma, strict=False):
                    if len(data) >= period:
                        sma = closes.rolling(window=period).mean()
                        ax.plot(
                            range(len(data)),
                            sma,
                            label=f"SMA{period}",
                            color=color,
                            linewidth=1.5,
                            alpha=0.7,
                        )

            # Format chart
            ax.set_title(title, fontsize=14, fontweight="bold")
            ax.set_xlabel("Time", fontsize=10)
            ax.set_ylabel("Price", fontsize=10)
            ax.grid(True, alpha=0.3)
            if show_sma:
                ax.legend(loc="upper left")

            # Format x-axis with time labels
            num_ticks = 10
            tick_indices = np.linspace(0, len(data) - 1, num_ticks, dtype=int)
            tick_labels = [data.index[i].strftime("%H:%M") for i in tick_indices]
            ax.set_xticks(tick_indices)
            ax.set_xticklabels(tick_labels, rotation=45)

            # Render to PNG
            buffer = io.BytesIO()
            fig.tight_layout()
            fig.savefig(buffer, format="png", dpi=100, bbox_inches="tight")
            buffer.seek(0)
            png_bytes: bytes = buffer.read()
            plt.close(fig)

            # Strip metadata
            png_clean = self._strip_metadata(png_bytes)

            # Cache result
            self.cache.set(cache_key, png_clean, ttl=self.cache_ttl)

            logger.info(f"Chart rendered: {title} ({len(png_clean)} bytes)")
            return png_clean

        except Exception as e:
            logger.error(f"Chart rendering failed: {e}", exc_info=True)
            raise

    def render_equity_curve(
        self,
        equity_points: pd.DataFrame,
        title: str = "Equity Curve",
        width: int = 1200,
        height: int = 600,
    ) -> bytes:
        """Render equity curve with drawdown visualization.

        Args:
            equity_points: DataFrame with (timestamp, equity, drawdown) columns
            title: Chart title
            width: Chart width in pixels
            height: Chart height in pixels

        Returns:
            PNG bytes (metadata stripped)
        """
        cache_key = self._gen_cache_key(f"equity_{title}_{len(equity_points)}")

        cached_img = self.cache.get(cache_key)
        if cached_img is not None:
            logger.debug(f"Cache hit: {cache_key}")
            return cast(bytes, cached_img)

        logger.debug(f"Rendering equity curve: {title}")

        try:
            fig, (ax1, ax2) = plt.subplots(
                2,
                1,
                figsize=(width / 100, height / 100),
                dpi=100,
                gridspec_kw={"height_ratios": [3, 1]},
            )

            equity_points = equity_points.copy()
            equity_points.index = pd.to_datetime(equity_points["timestamp"])

            # Plot equity curve
            ax1.plot(
                range(len(equity_points)),
                equity_points["equity"],
                color="blue",
                linewidth=2,
                label="Equity",
            )
            ax1.fill_between(
                range(len(equity_points)),
                equity_points["equity"],
                alpha=0.2,
                color="blue",
            )
            ax1.set_title(title, fontsize=14, fontweight="bold")
            ax1.set_ylabel("Equity ($)", fontsize=10)
            ax1.grid(True, alpha=0.3)
            ax1.legend(loc="upper left")

            # Plot drawdown
            ax2.fill_between(
                range(len(equity_points)),
                equity_points["drawdown"],
                color="red",
                alpha=0.5,
                label="Drawdown %",
            )
            ax2.set_xlabel("Time", fontsize=10)
            ax2.set_ylabel("Drawdown %", fontsize=10)
            ax2.grid(True, alpha=0.3)
            ax2.legend(loc="upper left")

            # Format x-axis
            num_ticks = 10
            tick_indices = np.linspace(0, len(equity_points) - 1, num_ticks, dtype=int)
            tick_labels = [
                equity_points.index[i].strftime("%Y-%m-%d") for i in tick_indices
            ]
            ax2.set_xticks(tick_indices)
            ax2.set_xticklabels(tick_labels, rotation=45)

            # Render to PNG
            buffer = io.BytesIO()
            fig.tight_layout()
            fig.savefig(buffer, format="png", dpi=100, bbox_inches="tight")
            buffer.seek(0)
            png_bytes: bytes = buffer.read()
            plt.close(fig)

            # Strip metadata
            png_clean = self._strip_metadata(png_bytes)

            # Cache result
            self.cache.set(cache_key, png_clean, ttl=self.cache_ttl)

            logger.info(f"Equity curve rendered: {title} ({len(png_clean)} bytes)")
            return png_clean

        except Exception as e:
            logger.error(f"Equity curve rendering failed: {e}", exc_info=True)
            raise

    @staticmethod
    def _strip_metadata(png_bytes: bytes) -> bytes:
        """Strip EXIF and other metadata from PNG.

        Args:
            png_bytes: PNG image bytes

        Returns:
            PNG bytes without metadata
        """
        try:
            # Load image, remove metadata, save clean
            img = Image.open(io.BytesIO(png_bytes))
            # Remove metadata by creating new image
            data = list(img.getdata())
            img_clean = Image.new(img.mode, img.size)
            img_clean.putdata(data)

            # Save without metadata
            buffer = io.BytesIO()
            img_clean.save(buffer, format="PNG", optimize=True)
            buffer.seek(0)
            return buffer.read()
        except Exception as e:
            logger.warning(f"Metadata stripping failed: {e}, returning original")
            return png_bytes

    @staticmethod
    def _gen_cache_key(prefix: str) -> str:
        """Generate deterministic cache key from prefix."""
        import hashlib

        return f"chart:{hashlib.md5(prefix.encode()).hexdigest()}"
