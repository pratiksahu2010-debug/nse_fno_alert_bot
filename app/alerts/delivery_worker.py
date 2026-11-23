import asyncio,logging,uuid,json
from datetime import datetime,timezone
from .telegram import TelegramClient
from .outbox import Outbox
from ..database.models import AlertDeliveryRow
log=logging.getLogger(__name__)
class DeliveryWorker:
    def __init__(self,session_factory,settings): self.Session=session_factory; self.settings=settings; self.worker=str(uuid.uuid4())
    async def run(self):
        if not self.settings.telegram_bot_token or not self.settings.telegram_chat_id:
            log.warning('Telegram credentials absent; persistent outbox will remain pending'); return
        client=TelegramClient(self.settings.telegram_bot_token,self.settings.telegram_chat_id)
        try:
            while True:
                row=None
                with self.Session() as s:
                    row=Outbox(s).lease(self.worker)
                    if row: row_id=row.id; alert_id=row.alert_id; body=row.body; attempt=row.attempts; lease_token=row.lease_owner
                if not row:
                    await asyncio.sleep(1); continue
                try:
                    response=await client.send(body)
                    with self.Session() as s:
                        s.add(AlertDeliveryRow(alert_id=alert_id,attempt=attempt,status='SENT',response_json=json.dumps(response)))
                        Outbox(s).complete(row_id,lease_token)
                except Exception as exc:
                    log.exception('Telegram delivery failed')
                    with self.Session() as s:
                        s.add(AlertDeliveryRow(alert_id=alert_id,attempt=attempt,status='FAILED',error=str(exc)[:1000]))
                        Outbox(s).fail(row_id,lease_token,str(exc))
                    delay=getattr(exc,'retry_after',min(2**min(attempt,8),120))
                    await asyncio.sleep(min(max(float(delay),1),300))
        finally: await client.close()
