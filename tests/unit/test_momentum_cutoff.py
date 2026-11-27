import pandas as pd
import app.strategies.momentum_explosion as mod
from app.strategies.momentum_explosion import MomentumExplosionStrategy

def make_frame(start):
    idx=pd.date_range(end=start,periods=22,freq='5min')
    df=pd.DataFrame({'open':[100.0]*21+[100.0],'high':[101.0]*21+[103.0],'low':[99.0]*21+[99.0],'close':[100.0]*21+[102.0],'volume':[100.0]*21+[200.0]},index=idx)
    return df

def patch_indicators(monkeypatch,df):
    monkeypatch.setattr(mod,'ema',lambda values,period:pd.Series([110.0 if period==9 else 100.0]*len(values),index=values.index))
    monkeypatch.setattr(mod,'atr',lambda frame,period:pd.Series([1.0]*len(frame),index=frame.index))
    monkeypatch.setattr(mod,'relative_volume',lambda frame:pd.Series([2.0]*len(frame),index=frame.index))
    monkeypatch.setattr(mod,'adx',lambda frame,period:pd.Series([30.0]*len(frame),index=frame.index))
    monkeypatch.setattr(mod,'rsi',lambda frame,period:pd.Series([60.0]*len(frame),index=frame.index))
    monkeypatch.setattr(mod,'session_vwap',lambda frame:pd.Series([99.0]*len(frame),index=frame.index))
    monkeypatch.setattr(mod,'macd_histogram',lambda values:pd.Series([1.0]*len(values),index=values.index))

def test_completed_candle_ending_exactly_1500_qualifies(monkeypatch):
    df=make_frame(pd.Timestamp('2026-01-01 14:55:00',tz='Asia/Kolkata')); patch_indicators(monkeypatch,df)
    sig=MomentumExplosionStrategy().evaluate('ABC',df)
    assert sig is not None and sig.timestamp.strftime('%H:%M')=='15:00'

def test_candle_ending_after_1500_is_rejected(monkeypatch):
    df=make_frame(pd.Timestamp('2026-01-01 15:00:00',tz='Asia/Kolkata')); patch_indicators(monkeypatch,df)
    assert MomentumExplosionStrategy().evaluate('ABC',df) is None
