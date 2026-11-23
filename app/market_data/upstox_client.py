import httpx,asyncio,random
from urllib.parse import quote
class UpstoxClient:
    BASE='https://api.upstox.com'
    def __init__(self,token,timeout=15):
        if not token: raise ValueError('UPSTOX_ACCESS_TOKEN is required')
        self.client=httpx.AsyncClient(timeout=httpx.Timeout(timeout),headers={'Authorization':f'Bearer {token}','Accept':'application/json'})
    async def close(self): await self.client.aclose()
    async def _get(self,path,params=None):
        for attempt in range(5):
            r=await self.client.get(self.BASE+path,params=params)
            if r.status_code==429 or r.status_code>=500:
                if attempt==4: r.raise_for_status()
                retry=r.headers.get('Retry-After')
                try: delay=float(retry) if retry else min(2**attempt+random.random(),20)
                except ValueError: delay=min(2**attempt+random.random(),20)
                await asyncio.sleep(delay); continue
            r.raise_for_status(); data=r.json()
            if data.get('status')=='error': raise RuntimeError(f'Upstox API error: {data}')
            return data
        raise RuntimeError('Upstox request retry budget exhausted')
    async def historical_candles(self,key,unit='minutes',interval=1,to_date=None,from_date=None):
        if not to_date: raise ValueError('to_date required')
        path=f'/v3/historical-candle/{quote(key,safe="")}/{unit}/{interval}/{to_date}'+(f'/{from_date}' if from_date else '')
        return await self._get(path)
    async def intraday_candles(self,key,unit='minutes',interval=1):
        return await self._get(f'/v3/historical-candle/intraday/{quote(key,safe="")}/{unit}/{interval}')
    async def authorize_market_feed(self): return await self._get('/v3/feed/market-data-feed/authorize')
    async def option_chain(self,underlying_key,expiry_date):
        return await self._get('/v2/option/chain',{'instrument_key':underlying_key,'expiry_date':expiry_date})
    async def instrument_master(self,exchange='NSE'):
        # Official BOD JSON URL from Upstox instruments page.
        url='https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz'
        async with httpx.AsyncClient(timeout=60,follow_redirects=True) as c:
            r=await c.get(url); r.raise_for_status(); return r.content
