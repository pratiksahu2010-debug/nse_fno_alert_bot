from datetime import time, timedelta
from zoneinfo import ZoneInfo
from .indicators import ema,atr,relative_volume
from ..signals.models import Signal
class MomentumExplosionStrategy:
    name="MOMENTUM_EXPLOSION"
    def __init__(self,fast=9,slow=21,atr_period=14,lookback=10,rvol_threshold=1.5,atr_expansion=1.2,cutoff="15:00",cooldown=30):
        self.fast=fast; self.slow=slow; self.atr_period=atr_period; self.lookback=lookback; self.rvol_threshold=rvol_threshold; self.atr_expansion=atr_expansion; self.cutoff=time.fromisoformat(cutoff); self.cooldown=cooldown; self.last_signal={}
    def evaluate(self,symbol,df):
        if len(df)<max(self.slow,self.atr_period,self.lookback+1)+1:return None
        c=df.iloc[-1]; ts=c.name.to_pydatetime() if hasattr(c.name,"to_pydatetime") else c.name
        # DataFrame index is the candle START; decisions are made at its completed END.
        candle_end = ts + timedelta(minutes=5)
        if candle_end.astimezone(ZoneInfo('Asia/Kolkata')).time().replace(tzinfo=None)>self.cutoff:return None
        efast=ema(df.close,self.fast).iloc[-1]; eslow=ema(df.close,self.slow).iloc[-1]; a=atr(df,self.atr_period).iloc[-1]
        if not a or a<=0:return None
        prior=df.iloc[-self.lookback-1:-1]; hi=prior.high.max(); lo=prior.low.min(); rv=relative_volume(df).iloc[-1]
        expansion=(c.high-c.low)>=self.atr_expansion*a; participation=rv>=self.rvol_threshold if rv==rv else False
        if not (expansion or participation):return None
        direction="CALL" if efast>eslow and c.close>hi and c.close>c.open else "PUT" if efast<eslow and c.close<lo and c.close<c.open else None
        if not direction:return None
        previous=self.last_signal.get(symbol)
        if previous and (ts-previous).total_seconds()<self.cooldown*60:return None
        self.last_signal[symbol]=ts
        return Signal.create(symbol,self.name,direction,"MOMENTUM_EXPANSION",candle_end,float(c.close),metadata={"ema_fast":float(efast),"ema_slow":float(eslow),"atr":float(a),"rvol":None if rv!=rv else float(rv),"structure_high":float(hi),"structure_low":float(lo)})
