import json
from datetime import date
from pathlib import Path
class MarketCalendar:
    def __init__(self, holidays=None, special_sessions=None):
        self.holidays=set(date.fromisoformat(x) if isinstance(x,str) else x for x in (holidays or []))
        self.special_sessions=special_sessions or {}
    @classmethod
    def from_file(cls,path):
        d=json.loads(Path(path).read_text()); return cls(d.get("holidays",[]),d.get("special_sessions",{}))
    def is_trading_day(self,d): return d.weekday()<5 and d not in self.holidays or d.isoformat() in self.special_sessions
    def session_times(self,d):
        x=self.special_sessions.get(d.isoformat())
        return (x["open"],x["close"]) if x else ("09:15","15:30")
