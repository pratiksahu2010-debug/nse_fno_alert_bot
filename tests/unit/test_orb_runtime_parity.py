from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd

from app.backtesting.engine import BacktestEngine
from app.market_data.models import Candle
from app.runtime import LiveRuntime
from app.strategies.orb_gap import ORBGapStrategy


def _runtime_for_orb(key, day):
    runtime = object.__new__(LiveRuntime)
    runtime.settings = SimpleNamespace(timezone="Asia/Kolkata", orb_range_minutes=15)
    runtime.orb = ORBGapStrategy()
    runtime.day_refs = {key: {"open": 100.0, "previous_close": 100.0}}
    runtime.open_ranges = {(key, day): {"high": 101.0, "low": 99.0, "count": 3}}
    runtime.orb_done = set()
    return runtime


def test_live_orb_keeps_scanning_after_first_post_range_candle_has_no_breakout():
    zone = ZoneInfo("Asia/Kolkata")
    day = datetime(2026, 1, 2, 9, 30, tzinfo=zone).date()
    key = "NSE_EQ|TEST"
    runtime = _runtime_for_orb(key, day)

    first_start = datetime(2026, 1, 2, 9, 30, tzinfo=zone)
    first = Candle(key, first_start, first_start.replace(minute=35), 100, 100.8, 99.8, 100.5, 100)
    assert runtime._evaluate_orb(first, "TEST", first.end) is None
    assert (key, day) not in runtime.orb_done

    second_start = datetime(2026, 1, 2, 9, 35, tzinfo=zone)
    second = Candle(key, second_start, second_start.replace(minute=40), 100.5, 102.5, 100.2, 102, 200)
    signal = runtime._evaluate_orb(second, "TEST", second.end)
    assert signal is not None
    assert signal.direction == "CALL"
    assert signal.timestamp == second.end
    # Candidate creation alone must not consume the day's opportunity.
    assert (key, day) not in runtime.orb_done
    runtime.orb_done.add((key, day))  # simulate successful durable persistence
    assert runtime._evaluate_orb(second, "TEST", second.end) is None


def test_live_orb_and_backtest_emit_same_later_breakout():
    zone = ZoneInfo("Asia/Kolkata")
    key = "NSE_EQ|TEST"
    day = datetime(2026, 1, 2, 9, 15, tzinfo=zone).date()
    idx = [
        datetime(2026, 1, 1, 15, 20, tzinfo=zone),
        datetime(2026, 1, 2, 9, 15, tzinfo=zone),
        datetime(2026, 1, 2, 9, 20, tzinfo=zone),
        datetime(2026, 1, 2, 9, 25, tzinfo=zone),
        datetime(2026, 1, 2, 9, 30, tzinfo=zone),
        datetime(2026, 1, 2, 9, 35, tzinfo=zone),
        datetime(2026, 1, 2, 9, 40, tzinfo=zone),
    ]
    frame = pd.DataFrame(
        {
            "open": [100, 100, 100, 100, 100, 100.5, 102],
            "high": [100, 101, 101, 101, 100.8, 102.5, 103],
            "low": [100, 99, 99, 99, 99.8, 100.2, 101],
            "close": [100, 100, 100, 100, 100.5, 102, 102.5],
            "volume": [100] * 7,
        },
        index=pd.DatetimeIndex(idx),
    )
    backtest = BacktestEngine(orb=ORBGapStrategy()).run_orb(frame, "TEST")
    assert len(backtest) == 1
    assert backtest.iloc[0]["direction"] == "CALL"
    assert backtest.iloc[0]["timestamp"] == idx[5] + pd.Timedelta(minutes=5)

    runtime = _runtime_for_orb(key, day)
    for i in (1, 2, 3):
        stamp = idx[i]
        candle = Candle(key, stamp, stamp + pd.Timedelta(minutes=5), frame.iloc[i].open, frame.iloc[i].high, frame.iloc[i].low, frame.iloc[i].close, frame.iloc[i].volume)
        runtime._evaluate_orb(candle, "TEST", candle.end)
    # First post-range candle is deliberately not a breakout.
    first = Candle(key, idx[4], idx[4] + pd.Timedelta(minutes=5), 100, 100.8, 99.8, 100.5, 100)
    assert runtime._evaluate_orb(first, "TEST", first.end) is None
    second = Candle(key, idx[5], idx[5] + pd.Timedelta(minutes=5), 100.5, 102.5, 100.2, 102, 100)
    live = runtime._evaluate_orb(second, "TEST", second.end)
    assert live is not None
    assert live.direction == backtest.iloc[0]["direction"]
    assert live.timestamp == backtest.iloc[0]["timestamp"]
    assert (key, day) not in runtime.orb_done
