from app.risk.trade_manager import TradeState
def test_tp1_then_breakeven_then_trailing_stop():
 s=TradeState(entry=100,stop=95,direction='CALL')
 assert s.on_candle(106,101,105,110)==['TP1_HIT'] and s.stop==100
 assert s.on_candle(104,102,105,110,swing=102)==[] and s.stop==102
 assert s.on_candle(103,101,105,110,swing=101)==['TRAILING_SL_HIT']
def test_same_bar_tp1_tp2_only_books_tp1():
 s=TradeState(entry=100,stop=95,direction='CALL')
 assert s.on_candle(112,99,105,110)==['TP1_HIT']
