from .candle_builder import CandleBuilder
from .models import Tick
class CandleEngine:
    def __init__(self): self.one=CandleBuilder(1); self.five=CandleBuilder(5); self.last_end={}
    def on_tick(self,tick):
        self.one.add(tick); self.five.add(tick)
        return self.one.flush_before(tick.timestamp), self.five.flush_before(tick.timestamp)
