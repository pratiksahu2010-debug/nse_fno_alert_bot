import asyncio, json, logging, random, time, uuid
import websockets
log=logging.getLogger(__name__)
class WebsocketManager:
    """Upstox V3 protobuf websocket with batched subscriptions and reconnect restoration."""
    def __init__(self,client,keys,decoder,on_tick,mode='full',stale_seconds=90,batch_size=500,before_connect=None):
        self.client=client; self.keys=list(dict.fromkeys(keys)); self.decoder=decoder; self.on_tick=on_tick
        self.mode=mode; self.stale_seconds=stale_seconds; self.batch_size=batch_size; self.last_seen={}; self.running=False; self.connected=False
        self.before_connect=before_connect
    async def _subscribe(self,ws):
        for i in range(0,len(self.keys),self.batch_size):
            msg={'guid':str(uuid.uuid4()),'method':'sub','data':{'mode':self.mode,'instrumentKeys':self.keys[i:i+self.batch_size]}}
            await ws.send(json.dumps(msg).encode())
    async def run(self):
        self.running=True; delay=1
        while self.running:
            try:
                # Backfill before opening the socket: large universes can take time
                # under the REST rate limit, and an idle authorized socket may expire.
                if self.before_connect is not None:
                    await self.before_connect()
                auth=await self.client.authorize_market_feed(); data=auth.get('data',{})
                url=data.get('authorized_redirect_uri') or data.get('authorizedRedirectUri')
                if not url: raise RuntimeError('Upstox authorize response missing authorized redirect URI')
                async with websockets.connect(url,ping_interval=20,ping_timeout=20,max_size=8_000_000,open_timeout=20) as ws:
                    self.connected=True
                    await self._subscribe(ws); delay=1
                    async for payload in ws:
                        if isinstance(payload,str):
                            log.warning('Ignoring unexpected text frame from V3 feed'); continue
                        for tick in self.decoder(payload):
                            self.last_seen[tick.instrument_key]=time.time(); await self.on_tick(tick)
            except asyncio.CancelledError: raise
            except Exception: log.exception('Upstox V3 stream disconnected')
            finally: self.connected=False
            if self.running: await asyncio.sleep(delay+random.random()); delay=min(delay*2,60)
    def stop(self): self.running=False
    def stale_keys(self):
        now=time.time(); return [k for k in self.keys if now-self.last_seen.get(k,0)>self.stale_seconds]
