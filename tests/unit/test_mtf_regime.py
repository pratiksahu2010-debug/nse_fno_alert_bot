import pandas as pd

from app.strategies.indicators import classify_market_regime, completed_15m_bars


def _bars(stamps):
    return pd.DataFrame(
        {"open": range(len(stamps)), "high": [x + 2 for x in range(len(stamps))],
         "low": [x - 1 for x in range(len(stamps))], "close": [x + 1 for x in range(len(stamps))],
         "volume": [100] * len(stamps)},
        index=pd.DatetimeIndex(stamps),
    )


def test_completed_15m_requires_three_contiguous_completed_5m_bars():
    idx = pd.date_range("2026-11-27 03:45:00+00:00", periods=5, freq="5min")
    bars = completed_15m_bars(_bars(idx))
    assert len(bars) == 1
    assert bars.iloc[0].open == 0
    assert bars.iloc[0].close == 3
    assert bars.iloc[0].volume == 300


def test_completed_15m_drops_partial_bucket_and_gaps():
    idx = pd.DatetimeIndex([
        "2026-11-27 03:45:00+00:00", "2026-11-27 03:50:00+00:00",
        "2026-11-27 04:00:00+00:00", "2026-11-27 04:05:00+00:00",
    ])
    assert completed_15m_bars(_bars(idx)).empty


def test_regime_classification_and_invalid_inputs():
    assert classify_market_regime(30, 110, 100, 5) == "TRENDING"
    assert classify_market_regime(12, 100.2, 100, 5) == "RANGING"
    assert classify_market_regime(21, 110, 100, 5) == "TRANSITION"
    assert classify_market_regime(None, 1, 1, 1) == "UNKNOWN"
