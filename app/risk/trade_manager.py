from dataclasses import dataclass

@dataclass
class TradeState:
    """Underlying-price lifecycle. Stops only ratchet toward profit; never widen risk."""
    status:str='ENTRY_ACTIVE'
    tp1_hit:bool=False
    stop:float=0.0
    entry:float=0.0
    direction:str='CALL'
    original_stop:float|None=None
    def __post_init__(self):
        if self.direction not in {'CALL','PUT'}: raise ValueError('direction must be CALL or PUT')
        if self.original_stop is None: self.original_stop=self.stop
        if self.direction=='CALL' and not self.original_stop<self.entry: raise ValueError('CALL stop must be below entry')
        if self.direction=='PUT' and not self.original_stop>self.entry: raise ValueError('PUT stop must be above entry')
    def on_candle(self,high,low,tp1,tp2,swing=None):
        events=[]
        if self.status in {'CLOSED','INVALIDATED','EXPIRED'}: return events
        # Stop has priority whenever OHLC cannot establish intrabar ordering.
        stopped=low<=self.stop if self.direction=='CALL' else high>=self.stop
        if stopped:
            self.status='CLOSED'; events.append('TRAILING_SL_HIT' if self.tp1_hit else 'SL_HIT'); return events
        if not self.tp1_hit:
            hit=high>=tp1 if self.direction=='CALL' else low<=tp1
            if hit:
                self.tp1_hit=True; self.stop=self.entry; self.status='BREAKEVEN_ACTIVE'; events.append('TP1_HIT')
                # Do not infer TP2 in the same OHLC bar: intrabar sequence is unknown.
                return events
        if self.tp1_hit:
            if swing is not None:
                if self.direction=='CALL': self.stop=max(self.stop,self.entry,float(swing))
                else: self.stop=min(self.stop,self.entry,float(swing))
            hit2=high>=tp2 if self.direction=='CALL' else low<=tp2
            if hit2: self.status='CLOSED'; events.append('TP2_HIT')
            else: self.status='TRAILING_ACTIVE'
        return events
