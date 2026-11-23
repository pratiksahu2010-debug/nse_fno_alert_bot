import httpx
class TelegramRateLimitError(RuntimeError):
    def __init__(self,message,retry_after): super().__init__(message); self.retry_after=retry_after
class TelegramClient:
    def __init__(self,token,chat_id):
        self.token=token; self.chat_id=chat_id; self.http=httpx.AsyncClient(timeout=httpx.Timeout(12))
    async def send(self,text):
        if not self.token or not self.chat_id: raise RuntimeError('Telegram credentials not configured')
        r=await self.http.post(f'https://api.telegram.org/bot{self.token}/sendMessage',json={'chat_id':self.chat_id,'text':text})
        try: data=r.json()
        except Exception: data={}
        if r.status_code==429:
            retry=(data.get('parameters') or {}).get('retry_after',5)
            raise TelegramRateLimitError('Telegram rate limit reached',float(retry))
        r.raise_for_status()
        if not data.get('ok'): raise RuntimeError(f'Telegram API rejected message: {data}')
        return data
    async def close(self): await self.http.aclose()
