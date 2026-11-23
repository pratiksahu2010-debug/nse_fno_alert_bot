from datetime import time
from zoneinfo import ZoneInfo
from .gap_detector import detect_gap
from ..signals.models import Signal
class ORBGapStrategy:
    name='ORB_GAP'
    def __init__(self,range_minutes=15,cutoff='11:30',min_gap=1.0): self.range_minutes=range_minutes; self.cutoff=time.fromisoformat(cutoff); self.min_gap=min_gap
    def evaluate(self,symbol,day_open,previous_close,opening_range_high,opening_range_low,candle,now,vwap=None,rvol=None):
        if now.astimezone(ZoneInfo('Asia/Kolkata')).time().replace(tzinfo=None)>self.cutoff or opening_range_high is None or opening_range_low is None:return None
        if not day_open or not previous_close or previous_close<=0:return None
        if candle.close>opening_range_high: direction='CALL'
        elif candle.close<opening_range_low: direction='PUT'
        else:return None
        gap=detect_gap(day_open,previous_close,self.min_gap)
        gapdir='CALL' if gap.direction=='GAP_UP' else 'PUT' if gap.direction=='GAP_DOWN' else None
        setup='GAP_AND_GO' if gapdir==direction else 'FAILED_GAP_REVERSAL' if gapdir and gapdir!=direction else 'ORB_BREAKOUT'
        return Signal.create(symbol,self.name,direction,setup,candle.end,candle.close,metadata={'gap_pct':gap.pct,'gap_class':gap.classification,'or_high':opening_range_high,'or_low':opening_range_low,'atr':max(candle.high-candle.low,0),'vwap':vwap,'rvol':rvol})
