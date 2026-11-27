from collections import OrderedDict
from datetime import datetime, timedelta
from math import isfinite

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
        # Deduplicate repeated LTPC updates only while their candle is open.
        # Closed-bar watermarks reject late repeats after these keys are released.
        self.seen = {}
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
        # Upstox LTPC carries last-traded quantity, not a cumulative candle
        # volume. The same last trade is repeated in subsequent feed updates;
        # count its quantity once per open candle using exchange trade identity.
        if not isinstance(t.timestamp, datetime) or t.timestamp.tzinfo is None:
            return []
        try:
            price = float(t.price)
            if not isfinite(price) or price <= 0:
                return []
            if t.last_qty is not None:
                last_qty = float(t.last_qty)
                if not isfinite(last_qty) or last_qty < 0:
                    return []
            else:
                last_qty = None
            if t.cumulative_volume is not None:
                cumulative = float(t.cumulative_volume)
                if not isfinite(cumulative) or cumulative < 0:
                    return []
            else:
                cumulative = None
        except (TypeError, ValueError, OverflowError):
            return []

        start = self._floor(t.timestamp)
        ident = (t.instrument_key, start)
        watermark = self.closed_watermark.get(t.instrument_key)
        if ident in self.closed or (watermark is not None and start <= watermark):
            return []
        dedup = (t.timestamp, price, cumulative, last_qty)
        bar_seen = self.seen.setdefault(ident, set())
        if dedup in bar_seen:
            return []
        bar_seen.add(dedup)

        if last_qty is not None:
            vol = last_qty
        elif cumulative is not None:
            prev = self.last_cum.get(t.instrument_key)
            vol = max(0.0, cumulative - prev) if prev is not None and cumulative >= prev else 0.0
            # A lower exchange cumulative counter is treated as a reset; the
            # uncertain reset interval contributes zero rather than fake volume.
            self.last_cum[t.instrument_key] = cumulative
        else:
            vol = 0.0

        bucket = self.current.setdefault(ident, [])
        bucket.append((t.timestamp, price, vol))
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
            self.seen.pop(ident, None)
        out.sort(key=lambda x: (x.end, x.instrument_key))
        while len(self.closed) > self.max_closed_candles:
            self.closed.popitem(last=False)
        return out
