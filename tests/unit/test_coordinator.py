from datetime import datetime,timezone
from app.signals.models import Signal
from app.signals.coordinator import SignalCoordinator
def test_confluence_and_conflict():
 c=SignalCoordinator();t=datetime.now(timezone.utc)
 a=Signal.create("ABC","ORB_GAP","CALL","ORB",t,100);b=Signal.create("ABC","MOMENTUM_EXPLOSION","CALL","MOM",t,100);d=Signal.create("ABC","MOMENTUM_EXPLOSION","PUT","MOM",t,100)
 assert c.accept(a).relation=="INDEPENDENT";assert c.accept(b).relation=="CONFLUENCE";assert c.accept(d).relation=="CONFLICT"


def test_classify_is_side_effect_free_until_accept():
 c=SignalCoordinator(); t=datetime.now(timezone.utc)
 a=Signal.create("ABC","ORB_GAP","CALL","ORB",t,100)
 assert c.classify(a).relation=="INDEPENDENT"
 assert a.signal_id not in c.ids
 assert c.by_symbol_day=={}
 assert c.accept(a) is a
 assert a.signal_id in c.ids

def test_duplicate_accept_does_not_add_a_second_relation_entry():
 c=SignalCoordinator(); t=datetime.now(timezone.utc)
 a=Signal.create("ABC","ORB_GAP","CALL","ORB",t,100)
 assert c.accept(a) is a
 assert c.accept(a) is None
 assert len(c.by_symbol_day[("ABC",t.date())])==1
