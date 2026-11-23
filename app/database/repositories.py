import json
from sqlalchemy.exc import IntegrityError
from .models import SignalRow,OutboxRow,TradeRow,RiskLevelRow,SignalEventRow
class SignalRepository:
    def __init__(self,session): self.s=session
    def save_with_alert(self,s,body,levels=None,trade_state=None):
        if self.s.get(SignalRow,s.signal_id): return False
        try:
            row=SignalRow(signal_id=s.signal_id,symbol=s.symbol,module=s.module,direction=s.direction,setup=s.setup,timestamp=s.timestamp,entry=s.entry,metadata_json=json.dumps(s.metadata),relation=s.relation)
            self.s.add(row); self.s.flush()
            self.s.add(OutboxRow(alert_id=s.signal_id,body=body))
            self.s.add(SignalEventRow(signal_id=s.signal_id,event='SIGNAL_CREATED',payload_json='{}'))
            if levels:
                self.s.add(RiskLevelRow(signal_id=s.signal_id,entry=levels['entry'],stop_loss=levels['sl'],target_1=levels['tp1'],target_2=levels['tp2']))
            if trade_state is not None:
                self.s.add(TradeRow(signal_id=s.signal_id,state_json=json.dumps(trade_state)))
            self.s.commit(); return True
        except IntegrityError:
            self.s.rollback(); return False
