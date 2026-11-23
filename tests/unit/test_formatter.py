from datetime import datetime,timezone
from app.signals.models import Signal
from app.alerts.formatter import format_signal
def test_put_uses_red_marker():
 s=Signal.create("ABC","ORB_GAP","PUT","ORB",datetime.now(timezone.utc),100)
 txt=format_signal(s,{"entry":100,"sl":105,"tp1":95,"tp2":90,"rr":2})
 assert "🔴" in txt and "no order" in txt
