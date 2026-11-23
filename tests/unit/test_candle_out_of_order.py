from datetime import datetime,timezone,timedelta
from app.market_data.candle_builder import CandleBuilder
from app.market_data.models import Tick
def test_out_of_order_ticks_preserve_open_close():
 b=CandleBuilder(5); t=datetime(2026,1,1,4,0,tzinfo=timezone.utc)
 b.add(Tick('X',t+timedelta(minutes=2),105,last_qty=1))
 b.add(Tick('X',t,100,last_qty=1))
 b.add(Tick('X',t+timedelta(minutes=4),103,last_qty=1))
 bar=b.flush_before(t+timedelta(minutes=5))[0]
 assert (bar.open,bar.high,bar.low,bar.close,bar.volume)==(100,105,100,103,3)
