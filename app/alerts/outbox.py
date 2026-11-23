from datetime import datetime,timezone,timedelta
import uuid
from sqlalchemy import select,or_
from ..database.models import OutboxRow
class Outbox:
    def __init__(self,session):self.s=session
    def lease(self,worker,seconds=60):
        now=datetime.now(timezone.utc)
        row=self.s.scalar(select(OutboxRow).where(or_(OutboxRow.status=="PENDING",(OutboxRow.status=="LEASED")&(OutboxRow.lease_until<now))).order_by(OutboxRow.id).with_for_update(skip_locked=True).limit(1))
        if not row:return None
        row.status="LEASED";row.lease_owner=f"{worker}:{uuid.uuid4().hex}";row.lease_until=now+timedelta(seconds=seconds);row.attempts+=1;self.s.commit();return row
    def complete(self,row_id,worker):
        row=self.s.get(OutboxRow,row_id)
        if row and row.status=="LEASED" and row.lease_owner==worker:row.status="SENT";row.lease_until=None;self.s.commit();return True
        return False
    def fail(self,row_id,worker,error,max_attempts=8):
        row=self.s.get(OutboxRow,row_id)
        if row and row.status=="LEASED" and row.lease_owner==worker:row.status="FAILED" if row.attempts>=max_attempts else "PENDING";row.last_error=str(error)[:1000];row.lease_until=None;self.s.commit()
