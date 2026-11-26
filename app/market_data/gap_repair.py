"""Validated parsing helpers for Upstox intraday candle gap repair."""
from datetime import datetime, timedelta, timezone
from math import isfinite
from zoneinfo import ZoneInfo

from .models import Candle


class CandleDataError(ValueError):
    """Raised when an exchange candle response is malformed or contradictory."""


def parse_upstox_candles(
    instrument_key,
    rows,
    interval_minutes,
    *,
    now=None,
    timezone_name="Asia/Kolkata",
):
    """Parse completed regular-session Upstox OHLCV rows into ordered candles.

    Upstox rows are [timestamp, open, high, low, close, volume, ...]. Naive
    timestamps, misaligned intervals, invalid OHLCV and conflicting duplicate
    timestamps are rejected rather than silently manufacturing market data.
    Incomplete bars and bars outside the regular NSE session are ignored.
    """
    if interval_minutes not in (1, 5):
        raise ValueError("only 1m and 5m candles are supported")
    if not isinstance(rows, (list, tuple)):
        raise CandleDataError("candle response must be a list")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    now = now.astimezone(timezone.utc)
    zone = ZoneInfo(timezone_name)
    delta = timedelta(minutes=interval_minutes)
    width = interval_minutes * 60
    parsed = {}

    for index, row in enumerate(rows):
        if not isinstance(row, (list, tuple)) or len(row) < 6:
            raise CandleDataError(f"row {index} has fewer than six OHLCV fields")
        try:
            stamp = datetime.fromisoformat(str(row[0]).replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                raise CandleDataError(f"row {index} timestamp has no timezone")
            start = stamp.astimezone(timezone.utc)
            values = tuple(float(value) for value in row[1:6])
        except CandleDataError:
            raise
        except (TypeError, ValueError, OverflowError) as exc:
            raise CandleDataError(f"row {index} contains an invalid timestamp or number") from exc

        open_, high, low, close, volume = values
        if int(start.timestamp()) % width:
            raise CandleDataError(f"row {index} timestamp is not {interval_minutes}m aligned")
        if not all(isfinite(value) for value in values):
            raise CandleDataError(f"row {index} contains a non-finite OHLCV value")
        if min(open_, high, low, close) <= 0 or volume < 0:
            raise CandleDataError(f"row {index} contains non-positive prices or negative volume")
        if high < max(open_, low, close) or low > min(open_, high, close):
            raise CandleDataError(f"row {index} violates OHLC invariants")

        end = start + delta
        local_start = start.astimezone(zone)
        session_start = local_start.replace(hour=9, minute=15, second=0, microsecond=0)
        session_end = local_start.replace(hour=15, minute=30, second=0, microsecond=0)
        if start < session_start.astimezone(timezone.utc) or end > session_end.astimezone(timezone.utc):
            continue
        if end > now:
            continue

        candle = Candle(instrument_key, start, end, open_, high, low, close, volume, "historical")
        previous = parsed.get(start)
        if previous is not None:
            if (previous.open, previous.high, previous.low, previous.close, previous.volume) != values:
                raise CandleDataError(f"conflicting duplicate candle at {start.isoformat()}")
            continue
        parsed[start] = candle

    return [parsed[start] for start in sorted(parsed)]
