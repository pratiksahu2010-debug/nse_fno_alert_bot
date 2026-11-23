import json
from pathlib import Path
class Universe:
    def __init__(self,path): self.path=Path(path); self.data=json.loads(self.path.read_text())
    @property
    def instruments(self): return self.data['instruments']
    def validate(self):
        rows=self.instruments; keys=[x.get('instrument_key') for x in rows]
        if not rows or any(not k for k in keys) or len(keys)!=len(set(keys)): raise ValueError('Universe is empty or has missing/duplicate keys')
        symbols={str(x.get('symbol','')).upper() for x in rows}
        if not any(x in symbols for x in ('NIFTY','NIFTY 50')): raise ValueError('NIFTY index missing from frozen universe')
        if not any(x in symbols for x in ('BANKNIFTY','NIFTY BANK')): raise ValueError('BANKNIFTY index missing from frozen universe')
        return True
    @property
    def version(self): return self.data.get('version','unknown')
