"""
PR-055: Chart Renderer for PNG Exports

Renders equity curves and analytics charts as PNG images.
Uses matplotlib with Agg backend (server-safe, no display required).
"""

from io import BytesIO

import matplotlib

# Use non-interactive backend (server-safe)
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.figure import Figure

from backend.app.analytics.equity_engine import EquitySeriesOut


class ChartRenderer:
    """Renders analytics charts as PNG images.

    Uses matplotlib with Agg backend for server-side rendering.
    Thread-safe and memory-efficient (BytesIO in-memory buffers).
    """

    def __init__(self, dpi: int = 150, figsize: tuple[int, int] = (12, 6)):
        """Initialize chart renderer.

        Args:
            dpi: Resolution (dots per inch). Higher = larger file. Default 150.
            figsize: Figure size in inches (width, height). Default (12, 6).
        """
        self.dpi = dpi
        self.figsize = figsize

    def render_equity_chart(
        self, equity_data: EquitySeriesOut, title: str | None = None
    ) -> bytes:
        """Render equity curve as PNG bytes.

        Args:
            equity_data: Equity series data from EquityEngine
            title: Chart title (default: "Equity Curve")

        Returns:
            PNG image as bytes (ready for StreamingResponse)

        Raises:
            ValueError: If equity_data has no points

        Example:
            >>> engine = EquityEngine(db)
            >>> equity_data = await engine.compute_equity_series(user_id="123")
            >>> renderer = ChartRenderer()
            >>> png_bytes = renderer.render_equity_chart(equity_data)
            >>> # Return as StreamingResponse
        """
        if not equity_data or not equity_data.points:
            raise ValueError("Cannot render chart: no equity data points")

        # Extract data
        dates = [point.date for point in equity_data.points]
        equity_values = [point.equity for point in equity_data.points]

        # Create figure
        fig = Figure(figsize=self.figsize, dpi=self.dpi)
        ax = fig.add_subplot(111)

        # Plot equity curve
        ax.plot(
            dates,
            equity_values,
            linewidth=2.5,
            color="#2E86AB",
            label="Equity",
            zorder=2,
        )

        # Add initial equity reference line
        ax.axhline(
            y=equity_data.initial_equity,
            color="#888888",
            linestyle="--",
            linewidth=1,
            label=f"Initial: {equity_data.initial_equity:,.2f}",
            zorder=1,
        )

        # Styling
        ax.set_title(
            title or "Equity Curve",
            fontsize=16,
            fontweight="bold",
            pad=20,
        )
        ax.set_xlabel("Date", fontsize=12, fontweight="bold")
        ax.set_ylabel("Equity", fontsize=12, fontweight="bold")
        ax.grid(True, alpha=0.3, linestyle="--", zorder=0)
        ax.legend(loc="best", fontsize=10)

        # Format dates on X-axis
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        fig.autofmt_xdate()  # Rotate date labels

        # Format Y-axis with commas
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"{x:,.0f}"))

        # Add summary annotation
        summary = (
            f"Total Return: {equity_data.total_return_percent:+.2f}%\n"
            f"Max Drawdown: {equity_data.max_drawdown_percent:.2f}%\n"
            f"Days: {equity_data.days_in_period}"
        )
        ax.text(
            0.02,
            0.98,
            summary,
            transform=ax.transAxes,
            fontsize=10,
            verticalalignment="top",
            bbox={
                "boxstyle": "round,pad=0.5",
                "facecolor": "white",
                "edgecolor": "#2E86AB",
                "alpha": 0.9,
            },
        )

        # Tight layout
        fig.tight_layout()

        # Save to bytes
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=self.dpi, bbox_inches="tight")
        buf.seek(0)
        png_bytes = buf.getvalue()

        # Clean up
        plt.close(fig)

        return png_bytes

    def render_win_rate_donut(
        self,
        win_rate: float,
        num_wins: int,
        num_losses: int,
        title: str | None = None,
    ) -> bytes:
        """Render win rate donut chart as PNG bytes.

        Args:
            win_rate: Win rate percentage (0-100)
            num_wins: Number of winning trades
            num_losses: Number of losing trades
            title: Chart title (default: "Win Rate")

        Returns:
            PNG image as bytes

        Example:
            >>> renderer = ChartRenderer()
            >>> png_bytes = renderer.render_win_rate_donut(
            ...     win_rate=65.5, num_wins=21, num_losses=11
            ... )
        """
        if num_wins + num_losses == 0:
            raise ValueError("Cannot render win rate: no trades")

        # Data
        sizes = [win_rate, 100 - win_rate]
        labels = [f"Wins: {num_wins}", f"Losses: {num_losses}"]
        colors = ["#2E86AB", "#E63946"]
        explode = (0.05, 0)  # Explode wins slice

        # Create figure
        fig = Figure(figsize=(8, 6), dpi=self.dpi)
        ax = fig.add_subplot(111)

        # Donut chart
        ax.pie(
            sizes,
            labels=labels,
            colors=colors,
            autopct="%1.1f%%",
            startangle=90,
            explode=explode,
            textprops={"fontsize": 12, "fontweight": "bold"},
            wedgeprops={"width": 0.4},  # Donut hole
        )

        # Styling
        ax.set_title(
            title or "Win Rate",
            fontsize=16,
            fontweight="bold",
            pad=20,
        )

        # Equal aspect ratio ensures circular shape
        ax.axis("equal")

        # Tight layout
        fig.tight_layout()

        # Save to bytes
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=self.dpi, bbox_inches="tight")
        buf.seek(0)
        png_bytes = buf.getvalue()

        # Clean up
        plt.close(fig)

        return png_bytes
