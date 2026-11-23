"""Event-driven underlying-price backtester. OHLC ambiguity is resolved conservatively."""
import pandas as pd
from datetime import timedelta
from ..strategies.orb_gap import ORBGapStrategy
from ..strategies.momentum_explosion import MomentumExplosionStrategy
from ..risk.stop_loss import structural_stop
from ..risk.targets import calculate_levels
from ..risk.trade_manager import TradeState
from ..strategies.indicators import atr

class BacktestEngine:
    def __init__(self,orb=None,momentum=None,slippage_bps=5,brokerage_per_trade=20,other_costs_per_trade=0):
        self.orb=orb or ORBGapStrategy(); self.momentum=momentum or MomentumExplosionStrategy()
        self.slip=slippage_bps/10000; self.fee=brokerage_per_trade+other_costs_per_trade
    def _simulate(self,df,i,sig,symbol):
        a=float(sig.metadata.get('atr') or 0)
        sl=structural_stop(sig,a)
        if sl is None:return None
        lv=calculate_levels(sig.entry,sl,sig.direction)
        state=TradeState(entry=sig.entry,stop=sl,direction=sig.direction)
        exit_price=None; reason='OPEN'; exit_ts=None; tp1_hit=False
        future=df.iloc[i+1:]
        for j,(ts,bar) in enumerate(future.iterrows()):
            prior=future.iloc[max(0,j-3):j]
            swing=None
            if len(prior): swing=float(prior.low.min() if sig.direction=='CALL' else prior.high.max())
            old_status=state.status
            events=state.on_candle(float(bar.high),float(bar.low),lv['tp1'],lv['tp2'],swing)
            if 'TP1_HIT' in events: tp1_hit=True
            if 'SL_HIT' in events or 'TRAILING_SL_HIT' in events:
                exit_price=sl if old_status=='ENTRY_ACTIVE' else state.stop; reason=events[0]; exit_ts=ts; break
            if 'TP2_HIT' in events: exit_price=lv['tp2']; reason='TP2_HIT'; exit_ts=ts; break
        if exit_price is None and len(future):
            exit_price=float(future.iloc[-1].close); exit_ts=future.index[-1]; reason='EOD'
        if exit_price is None:return None
        # Adverse slippage on both sides; CALL is long underlying, PUT is short underlying.
        if sig.direction=='CALL': entry_exec=sig.entry*(1+self.slip); exit_exec=exit_price*(1-self.slip); gross=exit_exec-entry_exec
        else: entry_exec=sig.entry*(1-self.slip); exit_exec=exit_price*(1+self.slip); gross=entry_exec-exit_exec
        pnl=gross-self.fee
        return {'signal_id':sig.signal_id,'symbol':symbol,'module':sig.module,'direction':sig.direction,'setup':sig.setup,'timestamp':sig.timestamp,'exit_timestamp':exit_ts,'entry':sig.entry,'entry_exec':entry_exec,'sl':sl,'tp1':lv['tp1'],'tp2':lv['tp2'],'exit':exit_price,'exit_exec':exit_exec,'reason':reason,'tp1_hit':tp1_hit,'gross_pnl':gross,'net_pnl':pnl,'fees':self.fee,'holding_minutes':(exit_ts-sig.timestamp).total_seconds()/60 if exit_ts is not None else 0}
    def run_momentum(self,df,symbol):
        history=df.sort_index().copy(); rows=[]; last_exit=-1
        for i in range(40,len(history)):
            if i<=last_exit: continue
            sig=self.momentum.evaluate(symbol,history.iloc[:i+1])
            if not sig:continue
            trade=self._simulate(history,i,sig,symbol)
            if trade:
                rows.append(trade)
                if trade['exit_timestamp'] is not None:last_exit=history.index.get_loc(trade['exit_timestamp'])
        return pd.DataFrame(rows)
    def run_orb(self,df,symbol):
        history=df.sort_index().copy(); rows=[]
        if history.empty:return pd.DataFrame(rows)
        # Separate by local session date; index timestamps should be timezone-aware IST or UTC.
        local_index=history.index.tz_convert('Asia/Kolkata') if history.index.tz is not None else history.index
        history=history.copy(); history['_session']=local_index.date
        dates=list(dict.fromkeys(history['_session'].tolist()))
        for di,day in enumerate(dates):
            daydf=history[history['_session']==day].drop(columns=['_session'])
            if len(daydf)<self.orb.range_minutes//5+2 or di==0:continue
            prevday=history[history['_session']==dates[di-1]].drop(columns=['_session'])
            prev_close=float(prevday.iloc[-1].close); day_open=float(daydf.iloc[0].open)
            n=self.orb.range_minutes//5; opening=daydf.iloc[:n]; hi=float(opening.high.max()); lo=float(opening.low.min())
            for j in range(n,len(daydf)):
                sig=self.orb.evaluate(symbol,day_open,prev_close,hi,lo, type('Bar',(),{'close':float(daydf.iloc[j].close),'high':float(daydf.iloc[j].high),'low':float(daydf.iloc[j].low),'end':daydf.index[j]+timedelta(minutes=5)})(),daydf.index[j]+timedelta(minutes=5))
                if sig:
                    # ORB stop buffer uses true range of the breakout bar as conservative volatility proxy.
                    sig.metadata['atr']=max(float(daydf.iloc[j].high-daydf.iloc[j].low),0.01)
                    trade=self._simulate(daydf,j,sig,symbol)
                    if trade: rows.append(trade)
                    break
        return pd.DataFrame(rows)
