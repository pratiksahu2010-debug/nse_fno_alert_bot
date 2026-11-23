from datetime import datetime,timezone,timedelta
from app.market_data.candle_builder import CandleBuilder
from app.market_data.models import Tick
def test_five_minute_bar_closes_only_after_boundary():
 b=CandleBuilder(5);t=datetime(2026,1,1,4,0,tzinfo=timezone.utc)
 b.add(Tick("X",t,100,last_qty=2));b.add(Tick("X",t+timedelta(minutes=4),105,last_qty=3))
 assert b.flush_before(t+timedelta(minutes=4,seconds=59))==[]
 out=b.flush_before(t+timedelta(minutes=5));assert len(out)==1 and out[0].high==105 and out[0].volume==5
