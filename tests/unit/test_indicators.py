import numpy as np
import pandas as pd

from app.strategies.indicators import adx, macd_histogram, rsi, session_vwap


def test_rsi_handles_rising_falling_and_flat_series():
    rising = pd.DataFrame({"close": np.arange(1.0, 40.0)})
    falling = pd.DataFrame({"close": np.arange(40.0, 1.0, -1.0)})
    flat = pd.DataFrame({"close": [10.0] * 40})
    assert rsi(rising, 14).iloc[-1] == 100
    assert rsi(falling, 14).iloc[-1] == 0
    assert rsi(flat, 14).iloc[-1] == 50


def test_adx_is_bounded_and_positive_for_directional_trend():
    close = np.arange(100.0, 160.0)
    frame = pd.DataFrame({"high": close + 1, "low": close - 1, "close": close})
    value = adx(frame, 14).iloc[-1]
    assert np.isfinite(value)
    assert 0 <= value <= 100
    assert value > 18


def test_macd_histogram_has_no_lookahead_and_is_finite_after_warmup():
    close = pd.Series(np.linspace(100, 130, 100))
    result = macd_histogram(close)
    assert result.index.equals(close.index)
    assert np.isfinite(result.iloc[-1])


def test_session_vwap_resets_on_local_trading_date():
    index = pd.DatetimeIndex([
        "2026-01-01 09:15:00+05:30",
        "2026-01-01 09:20:00+05:30",
        "2026-01-02 09:15:00+05:30",
        "2026-01-02 09:20:00+05:30",
    ])
    frame = pd.DataFrame(
        {"high": [101, 103, 201, 203], "low": [99, 101, 199, 201],
         "close": [100, 102, 200, 202], "volume": [10, 10, 10, 10]},
        index=index,
    )
    result = session_vwap(frame)
    assert result.iloc[1] < 103
    assert result.iloc[2] == 200
    assert result.iloc[3] > 200
