from datetime import timedelta
from collections import defaultdict
from .models import Tick,Candle

class CandleBuilder:
    """IST/epoch-aligned time bars. Ticks are deduped; out-of-order ticks are safe within open bars."""
    def __init__(self, minutes=1):
        if minutes not in (1,5): raise ValueError('only 1m and 5m bars are supported')
        self.minutes=minutes; self.delta=timedelta(minutes=minutes)
        self.current={}; self.seen=set(); self.closed={}; self.last_cum={}
    def _floor(self,dt):
        epoch=int(dt.timestamp()); width=self.minutes*60
        return __import__('datetime').datetime.fromtimestamp(epoch-epoch%width,tz=dt.tzinfo)
    def add(self,t:Tick):
        if t.price<=0: return []
        start=self._floor(t.timestamp); ident=(t.instrument_key,start)
        dedup=(t.instrument_key,t.timestamp,t.price,t.cumulative_volume,t.last_qty)
        if dedup in self.seen or ident in self.closed:return []
        self.seen.add(dedup)
        # Bounded dedup memory: keep only recent timestamps for active session.
        if len(self.seen)>100000: self.seen=set(list(self.seen)[-50000:])
        vol=max(0.0,float(t.last_qty or 0.0))
        if t.last_qty is None and t.cumulative_volume is not None:
            prev=self.last_cum.get(t.instrument_key); cur=float(t.cumulative_volume)
            vol=max(0.0,cur-prev) if prev is not None and cur>=prev else 0.0
            self.last_cum[t.instrument_key]=max(cur,prev or cur)
        bucket=self.current.setdefault(ident,[]); bucket.append((t.timestamp,float(t.price),vol))
        return []
    def flush_before(self,now):
        out=[]
        for ident,ticks in list(self.current.items()):
            start=ident[1]; end=start+self.delta
            if end>now: continue
            ticks.sort(key=lambda x:x[0])
            prices=[x[1] for x in ticks]
            candle=Candle(ident[0],start,end,prices[0],max(prices),min(prices),prices[-1],sum(x[2] for x in ticks))
            out.append(candle); self.closed[ident]=candle; del self.current[ident]
        out.sort(key=lambda x:(x.end,x.instrument_key))
        return out
