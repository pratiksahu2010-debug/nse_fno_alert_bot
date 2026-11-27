from datetime import datetime, timezone, timedelta

from app.market_data.candle_builder import CandleBuilder
from app.market_data.models import Tick


def test_five_minute_bar_closes_only_after_boundary():
    builder = CandleBuilder(5)
    start = datetime(2026, 1, 1, 4, 0, tzinfo=timezone.utc)
    builder.add(Tick("X", start, 100, last_qty=2))
    builder.add(Tick("X", start + timedelta(minutes=4), 105, last_qty=3))

    assert builder.flush_before(start + timedelta(minutes=4, seconds=59)) == []
    out = builder.flush_before(start + timedelta(minutes=5))
    assert len(out) == 1
    assert out[0].high == 105
    assert out[0].volume == 5


def test_closed_candle_cache_is_bounded_and_old_bars_cannot_reopen():
    builder = CandleBuilder(1, max_closed_candles=2)
    start = datetime(2026, 1, 1, 4, 0, tzinfo=timezone.utc)
    for minute in range(3):
        bar_start = start + timedelta(minutes=minute)
        builder.add(Tick("X", bar_start, 100 + minute, last_qty=1))
        assert len(builder.flush_before(bar_start + timedelta(minutes=1))) == 1
    assert len(builder.closed) == 2
    builder.add(Tick("X", start, 999, last_qty=1))
    assert builder.current == {}
    assert builder.flush_before(start + timedelta(minutes=4)) == []


def test_repeated_upstox_ltpc_trade_is_counted_once_per_open_candle():
    builder = CandleBuilder(5)
    start = datetime(2026, 1, 1, 4, 0, tzinfo=timezone.utc)
    repeated = Tick("X", start + timedelta(seconds=1), 100, last_qty=7)
    builder.add(repeated)
    builder.add(repeated)
    builder.add(Tick("X", start + timedelta(seconds=2), 100, last_qty=7))
    out = builder.flush_before(start + timedelta(minutes=5))
    assert len(out) == 1
    assert out[0].volume == 14


def test_cumulative_volume_deltas_are_used_instead_of_last_trade_quantity():
    builder = CandleBuilder(5)
    start = datetime(2026, 1, 1, 4, 0, tzinfo=timezone.utc)
    builder.add(Tick("X", start, 100, cumulative_volume=1000, last_qty=7))
    builder.add(Tick("X", start + timedelta(seconds=1), 101, cumulative_volume=1007, last_qty=7))
    builder.add(Tick("X", start + timedelta(seconds=1), 101, cumulative_volume=1007, last_qty=7))
    # A delayed packet is ignored for volume and must not rewind the baseline.
    builder.add(Tick("X", start + timedelta(milliseconds=500), 99, cumulative_volume=1003, last_qty=3))
    builder.add(Tick("X", start + timedelta(seconds=2), 102, cumulative_volume=1010, last_qty=3))
    out = builder.flush_before(start + timedelta(minutes=5))
    assert len(out) == 1
    assert out[0].volume == 10


def test_cumulative_counter_reset_at_new_exchange_day_rebaselines_safely():
    builder = CandleBuilder(1)
    start = datetime(2026, 1, 1, 4, 0, tzinfo=timezone.utc)
    builder.add(Tick("X", start, 100, cumulative_volume=1000))
    builder.add(Tick("X", start + timedelta(minutes=1), 101, cumulative_volume=1005))
    builder.flush_before(start + timedelta(minutes=2))
    next_day = start + timedelta(days=1)
    builder.add(Tick("X", next_day, 102, cumulative_volume=3))
    builder.add(Tick("X", next_day + timedelta(seconds=1), 103, cumulative_volume=8))
    out = builder.flush_before(next_day + timedelta(minutes=1))
    assert len(out) == 1
    assert out[0].volume == 5


def test_invalid_or_naive_ticks_are_rejected_without_corrupting_candle():
    builder = CandleBuilder(1)
    start = datetime(2026, 1, 1, 4, 0, tzinfo=timezone.utc)
    builder.add(Tick("X", start, float("nan"), last_qty=5))
    builder.add(Tick("X", start, float("inf"), last_qty=5))
    builder.add(Tick("X", start.replace(tzinfo=None), 100, last_qty=5))
    builder.add(Tick("X", start, 100, last_qty=float("nan")))
    builder.add(Tick("X", start + timedelta(seconds=1), 101, last_qty=2))
    out = builder.flush_before(start + timedelta(minutes=1))
    assert len(out) == 1
    assert (out[0].open, out[0].high, out[0].low, out[0].close, out[0].volume) == (101, 101, 101, 101, 2)


def test_dedup_state_is_released_when_bar_closes():
    builder = CandleBuilder(1)
    start = datetime(2026, 1, 1, 4, 0, tzinfo=timezone.utc)
    builder.add(Tick("X", start, 100, last_qty=1))
    assert len(builder.seen) == 1
    builder.flush_before(start + timedelta(minutes=1))
    assert builder.seen == {}
