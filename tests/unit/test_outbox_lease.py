from datetime import datetime,timezone,timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.database.connection import Base
from app.database.models import OutboxRow
from app.alerts.outbox import Outbox

def test_expired_lease_token_cannot_complete_new_attempt():
    engine=create_engine('sqlite:///:memory:'); Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(OutboxRow(alert_id='a1',body='alert')); s.commit()
        first=Outbox(s).lease('worker',seconds=0); old=first.lease_owner; rid=first.id
        # Force lease expiry and claim with a fresh fencing token.
        first.lease_until=datetime.now(timezone.utc)-timedelta(seconds=1); s.commit()
        second=Outbox(s).lease('worker',seconds=60); assert second.lease_owner!=old
        assert Outbox(s).complete(rid,old) is False
        assert Outbox(s).complete(rid,second.lease_owner) is True
