import pandas as pd
from app.strategies.momentum_explosion import MomentumExplosionStrategy
def test_requires_warmup():
 df=pd.DataFrame({"open":[1]*20,"high":[2]*20,"low":[.5]*20,"close":[1]*20,"volume":[100]*20},index=pd.date_range("2026-01-01 09:15",periods=20,freq="5min"))
 assert MomentumExplosionStrategy().evaluate("ABC",df) is None

import pandas as pd
import app.strategies.momentum_explosion as mod
from app.strategies.momentum_explosion import MomentumExplosionStrategy


def make_breakout_frame():
    idx = pd.date_range(end=pd.Timestamp("2026-01-01 14:55", tz="Asia/Kolkata"), periods=30, freq="5min")
    frame = pd.DataFrame({
        "open": [100.0] * 29 + [100.0],
        "high": [101.0] * 29 + [103.0],
        "low": [99.0] * 29 + [99.0],
        "close": [100.0] * 29 + [102.5],
        "volume": [100.0] * 29 + [250.0],
    }, index=idx)
    return frame


def patch_all_indicators(monkeypatch, frame, *, strength=30.0, volume=2.5, rsi_value=60.0, vwap_value=99.0, macd_value=1.0):
    def series(value):
        return pd.Series([value] * len(frame), index=frame.index)
    monkeypatch.setattr(mod, "ema", lambda values, period: series(110.0 if period == 9 else 100.0))
    monkeypatch.setattr(mod, "atr", lambda data, period: series(1.0))
    monkeypatch.setattr(mod, "relative_volume", lambda data: series(volume))
    monkeypatch.setattr(mod, "adx", lambda data, period: series(strength))
    monkeypatch.setattr(mod, "rsi", lambda data, period: series(rsi_value))
    monkeypatch.setattr(mod, "session_vwap", lambda data: series(vwap_value))
    monkeypatch.setattr(mod, "macd_histogram", lambda values: series(macd_value))


def test_momentum_signal_contains_confluence_score_and_indicator_evidence(monkeypatch):
    frame = make_breakout_frame()
    patch_all_indicators(monkeypatch, frame)
    signal = MomentumExplosionStrategy().evaluate("ABC", frame)
    assert signal is not None
    assert signal.direction == "CALL"
    assert signal.metadata["signal_score"] >= 75
    assert signal.metadata["adx"] == 30
    assert signal.metadata["rvol"] == 2.5
    assert signal.metadata["vwap_aligned"] is True
    assert signal.metadata["momentum_confirmed"] is True


def test_momentum_rejects_weak_adx_and_unconfirmed_volume(monkeypatch):
    frame = make_breakout_frame()
    patch_all_indicators(monkeypatch, frame, strength=17.9)
    assert MomentumExplosionStrategy().evaluate("LOW_ADX", frame) is None
    patch_all_indicators(monkeypatch, frame, strength=30, volume=1.49)
    assert MomentumExplosionStrategy().evaluate("LOW_VOLUME", frame) is None


def test_momentum_rejects_low_confluence_score(monkeypatch):
    frame = make_breakout_frame()
    patch_all_indicators(monkeypatch, frame, rsi_value=45, vwap_value=105, macd_value=-1)
    strategy = MomentumExplosionStrategy(min_score=75)
    assert strategy.evaluate("LOW_SCORE", frame) is None


def test_momentum_put_requires_downtrend_and_directional_confirmation(monkeypatch):
    frame = make_breakout_frame()
    frame.iloc[-1, frame.columns.get_loc("open")] = 102.0
    frame.iloc[-1, frame.columns.get_loc("close")] = 98.0
    frame.iloc[-1, frame.columns.get_loc("high")] = 103.0
    frame.iloc[-1, frame.columns.get_loc("low")] = 97.0
    frame.iloc[-11:-1, frame.columns.get_loc("high")] = 101.0
    frame.iloc[-11:-1, frame.columns.get_loc("low")] = 99.0
    patch_all_indicators(monkeypatch, frame)
    monkeypatch.setattr(mod, "ema", lambda values, period: pd.Series([90.0 if period == 9 else 100.0] * len(frame), index=frame.index))
    monkeypatch.setattr(mod, "rsi", lambda data, period: pd.Series([40.0] * len(frame), index=frame.index))
    monkeypatch.setattr(mod, "session_vwap", lambda data: pd.Series([99.0] * len(frame), index=frame.index))
    monkeypatch.setattr(mod, "macd_histogram", lambda values: pd.Series([-1.0] * len(frame), index=frame.index))
    signal = MomentumExplosionStrategy().evaluate("PUT_TEST", frame)
    assert signal is not None
    assert signal.direction == "PUT"
