from datetime import time, timedelta
from math import isfinite
from zoneinfo import ZoneInfo

from .indicators import (
    adx, atr, classify_market_regime, completed_15m_bars, ema,
    macd_histogram, relative_volume, rsi, session_vwap,
)
from ..signals.models import Signal


class MomentumExplosionStrategy:
    name = "MOMENTUM_EXPLOSION"

    def __init__(self, fast=9, slow=21, atr_period=14, lookback=10,
                 rvol_threshold=1.5, atr_expansion=1.2, cutoff="15:00",
                 cooldown=30, adx_min=18, min_score=75):
        self.fast, self.slow, self.atr_period, self.lookback = fast, slow, atr_period, lookback
        self.rvol_threshold, self.atr_expansion = rvol_threshold, atr_expansion
        self.cutoff, self.cooldown = time.fromisoformat(cutoff), cooldown
        self.adx_min, self.min_score = adx_min, min_score
        self.last_signal = {}

    @staticmethod
    def _number(value):
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return number if isfinite(number) else None

    def evaluate(self, symbol, df):
        required = max(self.slow, 2 * self.atr_period, self.lookback + 1) + 1
        if len(df) < required:
            return None
        candle = df.iloc[-1]
        stamp = candle.name.to_pydatetime() if hasattr(candle.name, "to_pydatetime") else candle.name
        if stamp.tzinfo is None:
            return None
        candle_end = stamp + timedelta(minutes=5)
        if candle_end.astimezone(ZoneInfo("Asia/Kolkata")).time().replace(tzinfo=None) > self.cutoff:
            return None

        fast_ema = self._number(ema(df.close, self.fast).iloc[-1])
        slow_ema = self._number(ema(df.close, self.slow).iloc[-1])
        current_atr = self._number(atr(df, self.atr_period).iloc[-1])
        current_rvol = self._number(relative_volume(df).iloc[-1])
        current_adx = self._number(adx(df, self.atr_period).iloc[-1])
        current_rsi = self._number(rsi(df, self.atr_period).iloc[-1])
        current_vwap = self._number(session_vwap(df).iloc[-1])
        current_macd_hist = self._number(macd_histogram(df.close).iloc[-1])
        close, open_price = self._number(candle.close), self._number(candle.open)
        high, low = self._number(candle.high), self._number(candle.low)
        values = (fast_ema, slow_ema, current_atr, current_rvol, current_adx,
                  current_rsi, current_vwap, current_macd_hist, close, open_price, high, low)
        if any(value is None for value in values) or current_atr <= 0 or high <= low:
            return None

        prior = df.iloc[-self.lookback - 1:-1]
        structure_high, structure_low = self._number(prior.high.max()), self._number(prior.low.min())
        if structure_high is None or structure_low is None:
            return None
        if fast_ema > slow_ema and close > structure_high and close > open_price:
            direction = "CALL"
        elif fast_ema < slow_ema and close < structure_low and close < open_price:
            direction = "PUT"
        else:
            return None
        if current_adx < self.adx_min or current_rvol < self.rvol_threshold:
            return None

        aligned_vwap = close > current_vwap if direction == "CALL" else close < current_vwap
        aligned_macd = current_macd_hist > 0 if direction == "CALL" else current_macd_hist < 0
        aligned_rsi = (50 <= current_rsi <= 75 if direction == "CALL" else 25 <= current_rsi <= 50)
        candle_range = high - low
        expansion = candle_range >= self.atr_expansion * current_atr
        body_ratio = abs(close - open_price) / candle_range
        close_location = (close - low) / candle_range
        quality_candle = (body_ratio >= 0.5 and close_location >= 0.7 if direction == "CALL"
                          else body_ratio >= 0.5 and close_location <= 0.3)
        score = 20
        score += 5 if (close > fast_ema if direction == "CALL" else close < fast_ema) else 0
        score += 10 if current_adx >= 25 else 7
        score += 10 if aligned_rsi else 4
        score += 10 if aligned_macd else 0
        score += 15 if aligned_vwap else 0
        score += 20 if current_rvol >= 2.0 else 15
        score += 5 if expansion else 0
        score += 5 if quality_candle else 0
        score = min(100, score)
        if score < self.min_score:
            return None
        previous = self.last_signal.get(symbol)
        if previous and (stamp - previous).total_seconds() < self.cooldown * 60:
            return None

        # 15m context is derived only from three fully completed 5m bars.
        # It is advisory metadata, not a hard gate while the 15m warmup is incomplete.
        bars_15m = completed_15m_bars(df)
        mtf_fast = mtf_slow = mtf_adx = None
        mtf_aligned = None
        if len(bars_15m) >= max(self.slow, 2 * self.atr_period):
            mtf_fast = self._number(ema(bars_15m.close, self.fast).iloc[-1])
            mtf_slow = self._number(ema(bars_15m.close, self.slow).iloc[-1])
            mtf_adx = self._number(adx(bars_15m, self.atr_period).iloc[-1])
            if mtf_fast is not None and mtf_slow is not None:
                mtf_aligned = mtf_fast > mtf_slow if direction == "CALL" else mtf_fast < mtf_slow
        regime = classify_market_regime(current_adx, fast_ema, slow_ema, current_atr)
        self.last_signal[symbol] = stamp
        return Signal.create(
            symbol, self.name, direction, "MOMENTUM_EXPANSION", candle_end, close,
            metadata={
                "ema_fast": fast_ema, "ema_slow": slow_ema, "atr": current_atr,
                "rvol": current_rvol, "adx": current_adx, "rsi": current_rsi,
                "vwap": current_vwap, "macd_histogram": current_macd_hist,
                "signal_score": score, "score_threshold": self.min_score,
                "structure_high": structure_high, "structure_low": structure_low,
                "volume_confirmed": True, "trend_confirmed": True,
                "vwap_aligned": aligned_vwap, "momentum_confirmed": aligned_macd,
                "market_regime": regime, "mtf_15m_ema_fast": mtf_fast,
                "mtf_15m_ema_slow": mtf_slow, "mtf_15m_adx": mtf_adx,
                "mtf_15m_aligned": mtf_aligned,
            },
        )
