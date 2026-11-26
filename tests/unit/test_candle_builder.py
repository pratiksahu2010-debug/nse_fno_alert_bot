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
    # The first candle has been evicted from the cache, but the watermark
    # still prevents a delayed tick from recreating it.
    builder.add(Tick("X", start, 999, last_qty=1))
    assert builder.current == {}
    assert builder.flush_before(start + timedelta(minutes=4)) == []
