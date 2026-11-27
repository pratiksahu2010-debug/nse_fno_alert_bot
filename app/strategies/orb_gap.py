from datetime import time
from zoneinfo import ZoneInfo
from .gap_detector import detect_gap
from ..signals.models import Signal


class ORBGapStrategy:
    name = "ORB_GAP"

    def __init__(self, range_minutes=15, cutoff="11:30", min_gap=1.0):
        self.range_minutes = range_minutes
        self.cutoff = time.fromisoformat(cutoff)
        self.min_gap = min_gap

    def evaluate(self, symbol, day_open, previous_close, opening_range_high,
                 opening_range_low, candle, now, vwap=None, rvol=None):
        if now.astimezone(ZoneInfo("Asia/Kolkata")).time().replace(tzinfo=None) > self.cutoff:
            return None
        if opening_range_high is None or opening_range_low is None:
            return None
        if not day_open or not previous_close or previous_close <= 0:
            return None
        if candle.close > opening_range_high:
            direction = "CALL"
        elif candle.close < opening_range_low:
            direction = "PUT"
        else:
            return None

        gap = detect_gap(day_open, previous_close, self.min_gap)
        gapdir = "CALL" if gap.direction == "GAP_UP" else "PUT" if gap.direction == "GAP_DOWN" else None
        setup = "GAP_AND_GO" if gapdir == direction else "FAILED_GAP_REVERSAL" if gapdir and gapdir != direction else "ORB_BREAKOUT"

        candle_range = max(float(candle.high) - float(candle.low), 0.0)
        body_ratio = abs(float(candle.close) - float(candle.open)) / candle_range if candle_range else 0.0
        close_location = (float(candle.close) - float(candle.low)) / candle_range if candle_range else 0.5
        directional_close = close_location >= 0.70 if direction == "CALL" else close_location <= 0.30
        vwap_aligned = None if vwap is None else (candle.close > vwap if direction == "CALL" else candle.close < vwap)
        volume_confirmed = None if rvol is None else rvol >= 1.5
        quality_score = 40
        quality_score += 15 if gapdir == direction else 0
        quality_score += 15 if vwap_aligned is True else 0
        quality_score += 15 if volume_confirmed is True else 0
        quality_score += 15 if body_ratio >= 0.5 and directional_close else 0

        return Signal.create(
            symbol, self.name, direction, setup, candle.end, candle.close,
            metadata={
                "gap_pct": gap.pct, "gap_class": gap.classification,
                "or_high": opening_range_high, "or_low": opening_range_low,
                "atr": candle_range, "vwap": vwap, "rvol": rvol,
                "orb_quality_score": quality_score, "orb_body_ratio": body_ratio,
                "orb_close_location": close_location, "orb_vwap_aligned": vwap_aligned,
                "orb_volume_confirmed": volume_confirmed,
            },
        )
