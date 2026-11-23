import asyncio
import httpx
import random
import time
from urllib.parse import quote


class UpstoxClient:
    BASE = "https://api.upstox.com"

    def __init__(self, token, timeout=15):
        if not token:
            raise ValueError("UPSTOX_ACCESS_TOKEN is required")
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        # Serialize REST requests and keep a conservative 5 requests/second ceiling.
        # Historical warm-up fans out across hundreds of symbols; uncontrolled bursts
        # cause Upstox 429s and prevent the live runtime from becoming ready.
        self._rate_lock = asyncio.Lock()
        self._last_request_at = 0.0
        self._min_request_interval = 0.20

    async def close(self):
        await self.client.aclose()

    async def _get(self, path, params=None):
        for attempt in range(5):
            async with self._rate_lock:
                wait = self._min_request_interval - (time.monotonic() - self._last_request_at)
                if wait > 0:
                    await asyncio.sleep(wait)
                response = await self.client.get(self.BASE + path, params=params)
                self._last_request_at = time.monotonic()
            if response.status_code == 429 or response.status_code >= 500:
                if attempt == 4:
                    response.raise_for_status()
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else min(2 ** attempt + random.random(), 20)
                except ValueError:
                    delay = min(2 ** attempt + random.random(), 20)
                await asyncio.sleep(delay)
                continue
            response.raise_for_status()
            data = response.json()
            if data.get("status") == "error":
                raise RuntimeError(f"Upstox API error: {data}")
            return data
        raise RuntimeError("Upstox request retry budget exhausted")

    async def historical_candles(self, key, unit="minutes", interval=1, to_date=None, from_date=None):
        if not to_date:
            raise ValueError("to_date required")
        path = f"/v3/historical-candle/{quote(key, safe='')}/{unit}/{interval}/{to_date}"
        if from_date:
            path += f"/{from_date}"
        return await self._get(path)

    async def intraday_candles(self, key, unit="minutes", interval=1):
        return await self._get(f"/v3/historical-candle/intraday/{quote(key, safe='')}/{unit}/{interval}")

    async def authorize_market_feed(self):
        return await self._get("/v3/feed/market-data-feed/authorize")

    async def option_chain(self, underlying_key, expiry_date):
        return await self._get(
            "/v2/option/chain",
            {"instrument_key": underlying_key, "expiry_date": expiry_date},
        )

    async def instrument_master(self, exchange="NSE"):
        # Official Upstox complete BOD instruments JSON.GZ file.
        url = "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content
