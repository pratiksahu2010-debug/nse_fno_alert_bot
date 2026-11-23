from dataclasses import dataclass,field
from datetime import datetime,timezone
import hashlib,json
@dataclass
class Signal:
    signal_id:str; symbol:str; module:str; direction:str; setup:str; timestamp:datetime; entry:float; metadata:dict=field(default_factory=dict); relation:str="INDEPENDENT"
    @classmethod
    def create(cls,symbol,module,direction,setup,timestamp,entry,metadata=None):
        stamp=timestamp.astimezone(timezone.utc).isoformat() if timestamp.tzinfo else timestamp.isoformat()
        raw=f"{symbol}|{module}|{direction}|{setup}|{stamp}"; sid=hashlib.sha256(raw.encode()).hexdigest()[:24]
        return cls(sid,symbol,module,direction,setup,timestamp,float(entry),metadata or {})
