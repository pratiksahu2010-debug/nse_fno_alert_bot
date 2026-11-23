from datetime import datetime
from zoneinfo import ZoneInfo
class MarketClock:
    def __init__(self,tz="Asia/Kolkata"): self.tz=ZoneInfo(tz)
    def now(self): return datetime.now(self.tz)
