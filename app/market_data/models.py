from dataclasses import dataclass
from datetime import datetime
@dataclass(frozen=True)
class Tick:
    instrument_key:str; timestamp:datetime; price:float; cumulative_volume:float|None=None; last_qty:float|None=None
@dataclass(frozen=True)
class Candle:
    instrument_key:str; start:datetime; end:datetime; open:float; high:float; low:float; close:float; volume:float; source:str="live"
