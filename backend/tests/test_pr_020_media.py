import pandas as pd

from backend.app.core.cache import get_cache_manager
from backend.app.media.render import ChartRenderer
from backend.app.media.storage import StorageManager


def make_ohlc_df(n=10):
    timestamps = pd.date_range("2025-01-01", periods=n, freq="min")
    opens = pd.Series([100 + i for i in range(n)])
    highs = opens + 1
    lows = opens - 1
    closes = opens + 0.5
    df = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
        }
    )
    return df


def test_render_candlestick_and_cache(tmp_path):
    cache = get_cache_manager()
    renderer = ChartRenderer(cache, cache_ttl=60)

    df = make_ohlc_df(20)
    img1 = renderer.render_candlestick(df, title="TestChart")
    assert isinstance(img1, (bytes, bytearray))
    assert len(img1) > 0

    # Second render should hit cache and return identical bytes
    img2 = renderer.render_candlestick(df, title="TestChart")
    assert img2 == img1


def test_equity_curve_render_and_storage(tmp_path):
    cache = get_cache_manager()
    renderer = ChartRenderer(cache, cache_ttl=60)

    # Create simple equity points
    timestamps = pd.date_range("2025-01-01", periods=5, freq="D")
    equity = pd.DataFrame(
        {
            "timestamp": timestamps,
            "equity": [1000, 1100, 1050, 1200, 1250],
            "drawdown": [0, 0, -4.5, 0, 0],
        }
    )

    img = renderer.render_equity_curve(equity, title="EquityTest")
    assert isinstance(img, (bytes, bytearray))
    assert len(img) > 0

    # Test storage save
    storage = StorageManager(base_path=str(tmp_path / "media_test"))
    path = storage.save_chart(img, user_id="u1", chart_name="equity_test")
    assert path.exists()
    assert path.stat().st_size > 0


def test_render_histogram_pnl_distribution(tmp_path):
    cache = get_cache_manager()
    renderer = ChartRenderer(cache, cache_ttl=60)

    # Create PnL distribution data
    pnl_data = pd.DataFrame(
        {
            "pnl": [10, 20, 15, 30, -5, 25, 18, 22, 12, 28, 5, 35, -10, 40],
        }
    )

    img = renderer.render_histogram(
        pnl_data, column="pnl", title="PnL Distribution", bins=10, color="green"
    )
    assert isinstance(img, (bytes, bytearray))
    assert len(img) > 0

    # Verify cache hit on second render
    img2 = renderer.render_histogram(
        pnl_data, column="pnl", title="PnL Distribution", bins=10, color="green"
    )
    assert img2 == img


def test_render_histogram_missing_column():
    cache = get_cache_manager()
    renderer = ChartRenderer(cache, cache_ttl=60)

    data = pd.DataFrame({"wrong_col": [1, 2, 3]})

    # When matplotlib is available, should raise ValueError
    # When not available, returns blank PNG gracefully
    try:
        result = renderer.render_histogram(data, column="value")
        # If we get here, matplotlib not available, returns blank PNG
        assert isinstance(result, (bytes, bytearray))
        assert len(result) > 0
    except ValueError as e:
        # matplotlib is available and raised error as expected
        assert "not found" in str(e)
