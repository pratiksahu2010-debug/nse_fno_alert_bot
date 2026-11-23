from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo
IST=ZoneInfo("Asia/Kolkata")
@dataclass(frozen=True)
class Session:
    trading_date: object
    open: time=time(9,15)
    close: time=time(15,30)
    def is_regular(self, dt):
        x=dt.astimezone(IST)
        return x.date()==self.trading_date and self.open <= x.time().replace(tzinfo=None) <= self.close
