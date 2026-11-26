"""Live alert-only orchestration. One worker owns the market feed and serial signal pipeline."""
import asyncio, logging
from datetime import datetime,timezone
import pandas as pd
from sqlalchemy.orm import sessionmaker
from .market_data.upstox_client import UpstoxClient
from .market_data.websocket_manager import WebsocketManager
from .market_data.protobuf_decoder import decode_market_data
from .market_data.candle_builder import CandleBuilder
from .market_data.models import Candle
from .market_data.gap_repair import parse_upstox_candles
from .market_data.universe import Universe
from .strategies.orb_gap import ORBGapStrategy
from .strategies.momentum_explosion import MomentumExplosionStrategy
from .signals.coordinator import SignalCoordinator
from .actors.shadow_runtime import ShadowActorRegistry
from .risk.stop_loss import structural_stop
from .risk.targets import calculate_levels
from .alerts.formatter import format_signal
from .database.repositories import SignalRepository
from .database.models import TradeRow,SignalRow,SignalEventRow
from .signals.models import Signal

from .alerts.delivery_worker import DeliveryWorker
log=logging.getLogger(__name__)

class LiveRuntime:
    def __init__(self,settings,engine,universe_path=None):
        self.settings=settings; self.engine=engine; self.Session=sessionmaker(bind=engine,expire_on_commit=False)
        self.universe=Universe(universe_path or settings.universe_path); self.universe.validate(); self.client=None; self.ws=None; self.tasks=[]; self.running=False
        self.one=CandleBuilder(1); self.five=CandleBuilder(5); self.one_hist={}; self.hist={}; self.day_refs={}; self.open_ranges={}; self.orb_done=set()
        self._repair_lock=asyncio.Lock(); self.repair_blocked_keys=set()
        self.orb=ORBGapStrategy(settings.orb_range_minutes,settings.orb_entry_cutoff,settings.gap_min_pct)
        self.momentum=MomentumExplosionStrategy(settings.ema_fast,settings.ema_slow,settings.atr_period,settings.structure_lookback,settings.relative_volume_threshold,settings.atr_expansion_threshold,settings.momentum_entry_cutoff,settings.momentum_cooldown_minutes)
        self.coordinator=SignalCoordinator()
        # Best-effort shadow observers; never authoritative for signals or alerts.
        self.shadow_actors=ShadowActorRegistry(mailbox_size=256,max_symbols=max(1,len(self.universe.instruments)))
    async def start(self):
        if not self.settings.upstox_access_token: raise RuntimeError('UPSTOX_ACCESS_TOKEN missing')
        self.client=UpstoxClient(self.settings.upstox_access_token)
        self.running=True
        self.shadow_actors.start()
        self.ws=WebsocketManager(self.client,[x['instrument_key'] for x in self.universe.instruments],decode_market_data,self.on_tick,stale_seconds=self.settings.websocket_stale_seconds,on_connect=self._repair_after_reconnect)
        await self._warmup()
        self._restore_module_state()
        self.tasks=[asyncio.create_task(self.ws.run(),name='upstox-v3-feed'),asyncio.create_task(DeliveryWorker(self.Session,self.settings).run(),name='telegram-outbox')]
        log.info('Runtime started: universe=%s instruments=%d strategies=ORB_GAP,MOMENTUM_EXPLOSION',self.universe.version,len(self.universe.instruments))
    async def stop(self):
        self.running=False
        if self.ws:self.ws.stop()
        for t in self.tasks:t.cancel()
        if self.tasks: await asyncio.gather(*self.tasks,return_exceptions=True)
        await self.shadow_actors.stop()
        shadow_summary=self.shadow_actors.snapshot(); shadow_summary.pop('actors',None)
        log.info('Shadow actor summary: %s',shadow_summary)
        if self.client: await self.client.close()
    async def _repair_after_reconnect(self):
        """Backfill completed session candles before the feed resumes live subscriptions.

        Historical bars rebuild indicator context but are deliberately not replayed
        through strategy evaluation, preventing stale retroactive Telegram alerts.
        A symbol whose repair request or payload validation fails remains blocked
        from signal processing until a later reconnect repairs it successfully.
        """
        from zoneinfo import ZoneInfo
        if not self.universe.instruments:
            return
        async with self._repair_lock:
            semaphore=asyncio.Semaphore(4)
            repaired=0
            failed=[]
            async def repair(inst):
                nonlocal repaired
                key=inst['instrument_key']
                try:
                    async with semaphore:
                        five_response=await self.client.intraday_candles(key,'minutes',5)
                        five_rows=five_response.get('data',{}).get('candles',[])
                        five=parse_upstox_candles(key,five_rows,5,timezone_name=self.settings.timezone)
                        one=[]
                        if self.one_hist.get(key):
                            one_response=await self.client.intraday_candles(key,'minutes',1)
                            one_rows=one_response.get('data',{}).get('candles',[])
                            one=parse_upstox_candles(key,one_rows,1,timezone_name=self.settings.timezone)
                    # Merge only candles newer than the last completed candle already
                    # retained. The websocket is not subscribed until this finishes.
                    last_five=self.hist.get(key,[])[-1].start if self.hist.get(key) else None
                    fresh_five=[c for c in five if last_five is None or c.start>last_five]
                    if fresh_five:
                        target=self.hist.setdefault(key,[])
                        target.extend(fresh_five)
                        if len(target)>1200: del target[:-1200]
                    last_one=self.one_hist.get(key,[])[-1].start if self.one_hist.get(key) else None
                    fresh_one=[c for c in one if last_one is None or c.start>last_one]
                    if fresh_one:
                        target=self.one_hist.setdefault(key,[])
                        target.extend(fresh_one)
                        if len(target)>1200: del target[:-1200]
                    self.repair_blocked_keys.discard(key)
                    repaired+=1
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.repair_blocked_keys.add(key)
                    failed.append(key)
                    log.warning('Candle gap repair failed for %s; signals remain blocked: %s',key,exc)
            await asyncio.gather(*(repair(inst) for inst in self.universe.instruments))
            log.info('Reconnect candle repair complete: repaired=%d/%d blocked=%d',repaired,len(self.universe.instruments),len(failed))

    async def on_tick(self,tick):
        # Never evaluate or alert on an instrument whose reconnect gap is unresolved.
        if tick.instrument_key in self.repair_blocked_keys:
            return
        # Non-blocking, bounded shadow fan-out. Signal processing below is unchanged.
        self.shadow_actors.submit(tick)
        self.one.add(tick); self.five.add(tick)
        now=tick.timestamp
        local=now.astimezone(__import__('zoneinfo').ZoneInfo(self.settings.timezone))
        if local.hour==9 and local.minute>=15 and local.minute<30:
            refs=self.day_refs.setdefault(tick.instrument_key,{})
            if 'open' not in refs and local.date()==datetime.now(__import__('zoneinfo').ZoneInfo(self.settings.timezone)).date(): refs['open']=tick.price
        for c in self.one.flush_before(now): self._remember(c,1)
        for c in self.five.flush_before(now): await self._on_five(c)
    def _restore_module_state(self):
        """Restore today's deduplication and Momentum cooldown state after Render restart."""
        from datetime import datetime,timezone
        from sqlalchemy import select
        from zoneinfo import ZoneInfo
        today=datetime.now(ZoneInfo(self.settings.timezone)).date()
        with self.Session() as s:
            rows=s.scalars(select(SignalRow).where(SignalRow.timestamp>=datetime.combine(today,datetime.min.time(),tzinfo=ZoneInfo(self.settings.timezone)).astimezone(timezone.utc))).all()
            key_by_symbol={x['symbol']:x['instrument_key'] for x in self.universe.instruments}
            for row in rows:
                sig=Signal(row.signal_id,row.symbol,row.module,row.direction,row.setup,row.timestamp,row.entry,{},row.relation)
                self.coordinator.ids.add(row.signal_id)
                self.coordinator.by_symbol_day.setdefault((row.symbol,row.timestamp.date()),[]).append(sig)
                if row.module=='MOMENTUM_EXPLOSION': self.momentum.last_signal[row.symbol]=row.timestamp
                if row.module=='ORB_GAP' and row.symbol in key_by_symbol: self.orb_done.add((key_by_symbol[row.symbol],today))
    async def _warmup(self):
        """Warm 5m indicators and prior close before accepting live entries."""
        from datetime import date,timedelta
        from zoneinfo import ZoneInfo
        from .market_data.models import Candle
        sem=asyncio.Semaphore(6); today=datetime.now(ZoneInfo(self.settings.timezone)).date(); end=today-timedelta(days=1); start=end-timedelta(days=28)
        async def load(inst):
            async with sem:
                key=inst['instrument_key']
                try:
                    hist=await self.client.historical_candles(key,'minutes',5,end.isoformat(),start.isoformat())
                    candles=hist.get('data',{}).get('candles',[])
                    parsed=[]
                    for row in reversed(candles):
                        ts=datetime.fromisoformat(row[0]); parsed.append(Candle(key,ts,ts+__import__('datetime').timedelta(minutes=5),float(row[1]),float(row[2]),float(row[3]),float(row[4]),float(row[5]),'historical'))
                    self.hist[key]=parsed[-500:]
                    # The final completed 5m candle in the historical response is the
                    # prior session close; avoid a separate daily endpoint call per symbol.
                    if parsed:
                        self.day_refs[key]={'previous_close':float(parsed[-1].close)}
                    # Fetch the true 09:15 regular-session open only while the market is
                    # open. Outside market hours ORB remains safely disabled until next day.
                    current=datetime.now(ZoneInfo(self.settings.timezone))
                    if __import__('datetime').time(9,15) <= current.time() <= __import__('datetime').time(15,30):
                        intra=await self.client.intraday_candles(key,'minutes',1)
                        today_rows=intra.get('data',{}).get('candles',[])
                        for bar in sorted(today_rows,key=lambda x:x[0]):
                            stamp=datetime.fromisoformat(bar[0]).astimezone(ZoneInfo(self.settings.timezone))
                            if stamp.date()==today and stamp.time().hour==9 and stamp.time().minute==15:
                                self.day_refs.setdefault(key,{})['open']=float(bar[1]); break
                except Exception as exc: log.warning('Warmup failed for %s: %s',key,exc)
        await asyncio.gather(*(load(x) for x in self.universe.instruments))
        log.info('Historical warmup complete: %d/%d instruments have 5m bars',sum(bool(self.hist.get(x['instrument_key'])) for x in self.universe.instruments),len(self.universe.instruments))
    def _remember(self,c,minutes):
        target=self.one_hist if minutes==1 else self.hist
        df=target.setdefault(c.instrument_key,[])
        # Historical repair can close bars that the live builder was still holding
        # when the socket dropped. Ignore those delayed duplicates after backfill.
        if df and c.start<=df[-1].start: return
        df.append(c)
        # Retain bounded rolling history.
        if len(df)>1200: del df[:-1200]
    async def _on_five(self,c):
        self._remember(c,5)
        rows=self.hist[c.instrument_key]
        await self._manage_trades(c, rows)
        if len(rows)<25:return
        df=pd.DataFrame([{'open':x.open,'high':x.high,'low':x.low,'close':x.close,'volume':x.volume} for x in rows],index=pd.DatetimeIndex(pd.to_datetime([x.start for x in rows],utc=True)))
        inst=next((x for x in self.universe.instruments if x['instrument_key']==c.instrument_key),None)
        if not inst:return
        symbol=inst['symbol']; now=c.end
        # Previous close and regular open are initialized from historical/live session data;
        # without validated refs the ORB strategy deliberately stays silent.
        refs=self.day_refs.get(c.instrument_key,{})
        sig=self.momentum.evaluate(symbol,df)
        if sig: await self._persist_signal(sig, c)
        # Opening range built strictly from completed regular-session 5m candles.
        local=now.astimezone(__import__('zoneinfo').ZoneInfo(self.settings.timezone))
        day=local.date(); start=local.replace(hour=9,minute=15,second=0,microsecond=0)
        range_end=start+__import__('datetime').timedelta(minutes=self.settings.orb_range_minutes)
        if c.start>=start and c.end<=range_end:
            state=self.open_ranges.setdefault((c.instrument_key,day),{'high':c.high,'low':c.low,'count':0})
            state['high']=max(state['high'],c.high); state['low']=min(state['low'],c.low); state['count']+=1
        elif c.end>range_end and (c.instrument_key,day) not in self.orb_done:
            state=self.open_ranges.get((c.instrument_key,day)); expected=self.settings.orb_range_minutes//5
            if state and state['count']>=expected and refs.get('open') and refs.get('previous_close'):
                orb=self.orb.evaluate(symbol,refs['open'],refs['previous_close'],state['high'],state['low'],c,now)
                self.orb_done.add((c.instrument_key,day))
                if orb: await self._persist_signal(orb,c)
    async def _manage_trades(self,c,rows):
        """Advance persisted trade lifecycle from completed underlying 5m bars."""
        import json
        from sqlalchemy import select
        from .risk.trade_manager import TradeState
        prior=rows[:-1][-3:]
        with self.Session() as s:
            records=s.execute(select(TradeRow,SignalRow).join(SignalRow,TradeRow.signal_id==SignalRow.signal_id).where(SignalRow.symbol==next((x['symbol'] for x in self.universe.instruments if x['instrument_key']==c.instrument_key),''))).all()
            for trade,signal in records:
                data=json.loads(trade.state_json)
                if data.get('state') in {'CLOSED','INVALIDATED','EXPIRED'}: continue
                state=TradeState(status=data.get('state','ENTRY_ACTIVE'),tp1_hit=bool(data.get('tp1_hit')),stop=float(data.get('trail_sl',data.get('original_sl'))),entry=float(data['entry']),direction=signal.direction,original_stop=float(data['original_sl']))
                swing=None
                if prior: swing=min(x.low for x in prior) if signal.direction=='CALL' else max(x.high for x in prior)
                events=state.on_candle(c.high,c.low,float(data['tp1']),float(data['tp2']),swing)
                if not events and state.status==data.get('state') and state.stop==float(data.get('trail_sl',data.get('original_sl'))): continue
                data.update({'state':state.status,'tp1_hit':state.tp1_hit,'trail_sl':state.stop})
                trade.state_json=json.dumps(data)
                for event in events: s.add(SignalEventRow(signal_id=trade.signal_id,event=event,payload_json=json.dumps({'stop':state.stop,'candle_end':c.end.isoformat()})))
            s.commit()
    async def _persist_signal(self,sig,candle):
        atr=float(sig.metadata.get('atr') or max(candle.high-candle.low,0))
        sl=structural_stop(sig,atr,self.settings.sl_atr_buffer)
        if sl is None: log.info('Rejected %s: structural stop unavailable',sig.signal_id); return
        levels=calculate_levels(sig.entry,sl,sig.direction,self.settings.target_1_r,self.settings.target_2_r)
        accepted=self.coordinator.accept(sig)
        if accepted is None:return
        body=format_signal(sig,levels)
        with self.Session() as s:
            repo=SignalRepository(s)
            repo.save_with_alert(sig,body,levels,{'state':'ENTRY_ACTIVE','entry':sig.entry,**levels,'original_sl':sl,'tp1_hit':False,'trail_sl':sl})
