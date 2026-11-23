from datetime import date
from app.market.calendar import MarketCalendar
def test_weekend_and_holiday():
 c=MarketCalendar(["2026-01-26"]);assert not c.is_trading_day(date(2026,1,25));assert not c.is_trading_day(date(2026,1,26))
