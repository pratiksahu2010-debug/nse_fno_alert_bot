from datetime import datetime, timedelta, timezone

import pytest

from app.market_data.gap_repair import CandleDataError, parse_upstox_candles


def _row(start, open_=100, high=103, low=99, close=102, volume=10):
    return [start.isoformat(), open_, high, low, close, volume]


def test_parser_sorts_rows_and_deduplicates_identical_timestamps():
    start = datetime(2026, 11, 26, 3, 45, tzinfo=timezone.utc)  # 09:15 IST
    later = start + timedelta(minutes=5)
    rows = [_row(later), _row(start), _row(start)]
    candles = parse_upstox_candles(
        "NSE_EQ|TEST", rows, 5, now=later + timedelta(minutes=5)
    )
    assert [c.start for c in candles] == [start, later]
    assert all(c.source == "historical" for c in candles)


def test_parser_ignores_incomplete_and_out_of_session_bars():
    start = datetime(2026, 11, 26, 3, 45, tzinfo=timezone.utc)
    incomplete = start + timedelta(minutes=5)
    before_open = start - timedelta(minutes=5)
    candles = parse_upstox_candles(
        "X",
        [_row(start), _row(incomplete), _row(before_open)],
        5,
        now=start + timedelta(minutes=9),
    )
    assert [c.start for c in candles] == [start]


@pytest.mark.parametrize(
    "row",
    [
        ["2026-11-26T03:45:00", 100, 103, 99, 102, 10],
        ["2026-11-26T03:46:00+00:00", 100, 103, 99, 102, 10],
        ["2026-11-26T03:45:00+00:00", 100, 98, 99, 102, 10],
        ["2026-11-26T03:45:00+00:00", 100, 103, 99, 102, -1],
        ["2026-11-26T03:45:00+00:00", 100, float("nan"), 99, 102, 10],
    ],
)
def test_parser_rejects_bad_timestamps_alignment_ohlc_and_volume(row):
    with pytest.raises(CandleDataError):
        parse_upstox_candles("X", [row], 5, now=datetime(2026, 11, 26, 4, 0, tzinfo=timezone.utc))


def test_parser_rejects_conflicting_duplicate_timestamp():
    start = datetime(2026, 11, 26, 3, 45, tzinfo=timezone.utc)
    with pytest.raises(CandleDataError, match="conflicting duplicate"):
        parse_upstox_candles(
            "X",
            [_row(start), _row(start, close=101)],
            5,
            now=start + timedelta(minutes=5),
        )


def test_parser_rejects_naive_now():
    with pytest.raises(ValueError, match="timezone-aware"):
        parse_upstox_candles("X", [], 5, now=datetime(2026, 11, 26, 4, 0))


def test_parser_accepts_one_minute_candles():
    start = datetime(2026, 11, 26, 3, 45, tzinfo=timezone.utc)
    candles = parse_upstox_candles(
        "X", [_row(start)], 1, now=start + timedelta(minutes=1)
    )
    assert len(candles) == 1
    assert candles[0].end - candles[0].start == timedelta(minutes=1)
