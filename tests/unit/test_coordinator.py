from datetime import datetime,timezone
from app.signals.models import Signal
from app.signals.coordinator import SignalCoordinator
def test_confluence_and_conflict():
 c=SignalCoordinator();t=datetime.now(timezone.utc)
 a=Signal.create("ABC","ORB_GAP","CALL","ORB",t,100);b=Signal.create("ABC","MOMENTUM_EXPLOSION","CALL","MOM",t,100);d=Signal.create("ABC","MOMENTUM_EXPLOSION","PUT","MOM",t,100)
 assert c.accept(a).relation=="INDEPENDENT";assert c.accept(b).relation=="CONFLUENCE";assert c.accept(d).relation=="CONFLICT"
