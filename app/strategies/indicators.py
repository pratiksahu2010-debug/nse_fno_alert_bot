import numpy as np
import pandas as pd


def ema(values, period):
    return values.ewm(span=period, adjust=False, min_periods=period).mean()


def _true_range(df):
    previous = df.close.shift(1)
    return pd.concat(
        [
            (df.high - df.low).abs(),
            (df.high - previous).abs(),
            (df.low - previous).abs(),
        ],
        axis=1,
    ).max(axis=1)


def atr(df, period=14):
    return _true_range(df).rolling(period, min_periods=period).mean()


def relative_volume(df, period=20):
    # Current completed bar vs preceding bars only; no look-ahead leakage.
    baseline = df.volume.shift(1).rolling(period, min_periods=period).mean()
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
    result = result.mask((average_gain == 0) & (average_loss == 0), 50)
    return result


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
    if df.index.tz is None:
        local_index = df.index.tz_localize(timezone_name)
    else:
        local_index = df.index.tz_convert(timezone_name)
    typical_price = (df.high + df.low + df.close) / 3
    volume = df.volume.clip(lower=0)
    weighted_price = typical_price * volume
    session_keys = pd.Series(local_index.date, index=df.index)
    cumulative_value = weighted_price.groupby(session_keys).cumsum()
    cumulative_volume = volume.groupby(session_keys).cumsum()
    return cumulative_value / cumulative_volume.where(cumulative_volume > 0)
