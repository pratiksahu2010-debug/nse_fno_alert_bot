class SignalCoordinator:
    def __init__(self): self.by_symbol_day={}; self.ids=set()
    def accept(self,s):
        if s.signal_id in self.ids:return None
        key=(s.symbol,s.timestamp.date()); prior=self.by_symbol_day.setdefault(key,[])
        same=[x for x in prior if x.direction==s.direction]; opp=[x for x in prior if x.direction!=s.direction]
        s.relation="CONFLICT" if opp else "CONFLUENCE" if same else "INDEPENDENT"
        self.ids.add(s.signal_id); prior.append(s); return s
