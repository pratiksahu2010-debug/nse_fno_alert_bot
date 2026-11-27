import numpy as np
import pandas as pd


def ema(values, period):
    return values.ewm(span=period, adjust=False, min_periods=period).mean()


def _true_range(df):
    previous = df.close.shift(1)
    return pd.concat(
        [(df.high - df.low).abs(), (df.high - previous).abs(), (df.low - previous).abs()],
        axis=1,
    ).max(axis=1)


def atr(df, period=14):
    return _true_range(df).rolling(period, min_periods=period).mean()


def relative_volume(df, period=20):
    """Compare volume with prior bars from the same local session only.

    Five prior same-session bars are the minimum baseline; this avoids using
    the previous session's closing volume to judge today's opening activity.
    """
    if isinstance(df.index, pd.DatetimeIndex):
        local_index = (
            df.index.tz_localize("Asia/Kolkata")
            if df.index.tz is None
            else df.index.tz_convert("Asia/Kolkata")
        )
        session = pd.Series(local_index.date, index=df.index)
        min_periods = min(period, 5)
        baseline = df.volume.groupby(session, sort=False).transform(
            lambda values: values.shift(1).rolling(period, min_periods=min_periods).mean()
        )
    else:
        baseline = df.volume.shift(1).rolling(period, min_periods=min(period, 5)).mean()
    return df.volume / baseline.where(baseline > 0)


def rsi(df, period=14):
    change = df.close.diff()
    gains = change.clip(lower=0)
    losses = -change.clip(upper=0)
    average_gain = gains.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    average_loss = losses.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    relative_strength = average_gain / average_loss.replace(0, np.nan)
    result = 100 - (100 / (1 + relative_strength))
    result = result.mask((average_loss == 0) & (average_gain > 0), 100)
    result = result.mask((average_gain == 0) & (average_loss > 0), 0)
    return result.mask((average_gain == 0) & (average_loss == 0), 50)


def adx(df, period=14):
    up_move = df.high.diff()
    down_move = -df.low.diff()
    positive_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    negative_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    true_range = _true_range(df)
    smoothed_tr = true_range.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    positive_di = 100 * positive_dm.ewm(alpha=1 / period, adjust=False, min_periods=period).mean() / smoothed_tr.replace(0, np.nan)
    negative_di = 100 * negative_dm.ewm(alpha=1 / period, adjust=False, min_periods=period).mean() / smoothed_tr.replace(0, np.nan)
    denominator = (positive_di + negative_di).replace(0, np.nan)
    dx = 100 * (positive_di - negative_di).abs() / denominator
    return dx.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def macd_histogram(values, fast=12, slow=26, signal=9):
    fast_line = values.ewm(span=fast, adjust=False, min_periods=fast).mean()
    slow_line = values.ewm(span=slow, adjust=False, min_periods=slow).mean()
    macd_line = fast_line - slow_line
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return macd_line - signal_line


def session_vwap(df, timezone_name="Asia/Kolkata"):
    """Cumulative typical-price VWAP, reset at each local trading-session date."""
    if not isinstance(df.index, pd.DatetimeIndex):
        return pd.Series(np.nan, index=df.index, dtype=float)
    local_index = df.index.tz_localize(timezone_name) if df.index.tz is None else df.index.tz_convert(timezone_name)
    typical_price = (df.high + df.low + df.close) / 3
    volume = df.volume.clip(lower=0)
    keys = pd.Series(local_index.date, index=df.index)
    return (typical_price * volume).groupby(keys).cumsum() / volume.groupby(keys).cumsum().where(volume.groupby(keys).cumsum() > 0)


def completed_15m_bars(df, timezone_name="Asia/Kolkata"):
    """Aggregate only full, contiguous groups of three completed 5m session bars."""
    if not isinstance(df.index, pd.DatetimeIndex) or df.index.tz is None or df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    local = df.copy()
    local.index = local.index.tz_convert(timezone_name)
    minute = local.index.hour * 60 + local.index.minute
    session_offset = minute - (9 * 60 + 15)
    valid = (session_offset >= 0) & (session_offset < 375)
    local = local.loc[valid].copy()
    if local.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    minute = local.index.hour * 60 + local.index.minute
    bucket = ((minute - 555) // 15).astype(int)
    keys = pd.MultiIndex.from_arrays([local.index.date, bucket])
    bars = []
    stamps = []
    for (_, _), group in local.groupby(keys, sort=True):
        if len(group) != 3:
            continue
        times = group.index
        if not (times[1] - times[0] == pd.Timedelta(minutes=5) and times[2] - times[1] == pd.Timedelta(minutes=5)):
            continue
        if times[0].minute not in (0, 15, 30, 45) and times[0].hour != 9:
            # Bucket validation below is authoritative; this guards malformed indexes.
            pass
        bars.append({
            "open": float(group.open.iloc[0]), "high": float(group.high.max()),
            "low": float(group.low.min()), "close": float(group.close.iloc[-1]),
            "volume": float(group.volume.sum()),
        })
        stamps.append(times[0].tz_convert("UTC"))
    if not bars:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    return pd.DataFrame(bars, index=pd.DatetimeIndex(stamps))


def classify_market_regime(adx_value, fast_ema, slow_ema, atr_value):
    """Deterministic regime label; never treats missing/invalid inputs as a trend."""
    values = (adx_value, fast_ema, slow_ema, atr_value)
    try:
        adx_value, fast_ema, slow_ema, atr_value = map(float, values)
    except (TypeError, ValueError, OverflowError):
        return "UNKNOWN"
    if not all(np.isfinite(value) for value in (adx_value, fast_ema, slow_ema, atr_value)) or atr_value <= 0:
        return "UNKNOWN"
    separation = abs(fast_ema - slow_ema) / atr_value
    if adx_value >= 25 and separation >= 0.15:
        return "TRENDING"
    if adx_value < 18 and separation < 0.10:
        return "RANGING"
    return "TRANSITION"
