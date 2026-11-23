from sqlalchemy import select
from .models import TradeRow,OutboxRow

def pending_outbox(session,limit=50): return list(session.scalars(select(OutboxRow).where(OutboxRow.status=="PENDING").limit(limit)))
def restore_trades(session): return {x.signal_id:x.state_json for x in session.scalars(select(TradeRow))}
