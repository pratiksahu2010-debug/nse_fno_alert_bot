from collections import OrderedDict, defaultdict
from datetime import timedelta

from .models import Tick, Candle


class CandleBuilder:
    """IST/epoch-aligned time bars with bounded closed-bar retention.

    Out-of-order ticks are accepted while a bar is open. Once an instrument's
    bar has closed, its watermark prevents that bar (or any older bar) from
    being reopened even after its candle is evicted from the bounded cache.
    """

    def __init__(self, minutes=1, max_closed_candles=10000):
        if minutes not in (1, 5):
            raise ValueError("only 1m and 5m bars are supported")
        if max_closed_candles < 1:
            raise ValueError("max_closed_candles must be positive")
        self.minutes = minutes
        self.delta = timedelta(minutes=minutes)
        self.max_closed_candles = max_closed_candles
        self.current = {}
        self.seen = set()
        self.closed = OrderedDict()
        self.closed_watermark = {}
        self.last_cum = {}

    def _floor(self, dt):
        epoch = int(dt.timestamp())
        width = self.minutes * 60
        return __import__("datetime").datetime.fromtimestamp(
            epoch - epoch % width, tz=dt.tzinfo
        )

    def add(self, t: Tick):
        if t.price <= 0:
            return []
        start = self._floor(t.timestamp)
        ident = (t.instrument_key, start)
        watermark = self.closed_watermark.get(t.instrument_key)
        if ident in self.closed or (watermark is not None and start <= watermark):
            return []
        dedup = (
            t.instrument_key,
            t.timestamp,
            t.price,
            t.cumulative_volume,
            t.last_qty,
        )
        if dedup in self.seen:
            return []
        self.seen.add(dedup)
        # Bound dedup memory for long-running market sessions.
        if len(self.seen) > 100000:
            self.seen = set(list(self.seen)[-50000:])
        vol = max(0.0, float(t.last_qty or 0.0))
        if t.last_qty is None and t.cumulative_volume is not None:
            prev = self.last_cum.get(t.instrument_key)
            cur = float(t.cumulative_volume)
            vol = max(0.0, cur - prev) if prev is not None and cur >= prev else 0.0
            self.last_cum[t.instrument_key] = max(cur, prev or cur)
        bucket = self.current.setdefault(ident, [])
        bucket.append((t.timestamp, float(t.price), vol))
        return []

    def flush_before(self, now):
        out = []
        for ident, ticks in list(self.current.items()):
            start = ident[1]
            end = start + self.delta
            if end > now:
                continue
            ticks.sort(key=lambda x: x[0])
            prices = [x[1] for x in ticks]
            candle = Candle(
                ident[0],
                start,
                end,
                prices[0],
                max(prices),
                min(prices),
                prices[-1],
                sum(x[2] for x in ticks),
            )
            out.append(candle)
            self.closed[ident] = candle
            previous = self.closed_watermark.get(ident[0])
            if previous is None or start > previous:
                self.closed_watermark[ident[0]] = start
            del self.current[ident]
        out.sort(key=lambda x: (x.end, x.instrument_key))
        while len(self.closed) > self.max_closed_candles:
            self.closed.popitem(last=False)
        return out
