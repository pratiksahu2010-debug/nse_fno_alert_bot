import asyncio,logging,uuid,json
from .telegram import TelegramClient
from .outbox import Outbox
from ..database.models import AlertDeliveryRow
log=logging.getLogger(__name__)


def record_delivery_success(session_factory,row_id,alert_id,attempt,lease_token,response):
    """Atomically record SENT only when this worker still owns the lease."""
    with session_factory() as session:
        session.add(AlertDeliveryRow(alert_id=alert_id,attempt=attempt,status="SENT",response_json=json.dumps(response)))
        if not Outbox(session).complete(row_id,lease_token):
            session.rollback()
            return False
        # Outbox.complete commits the delivery audit row and SENT transition together.
        return True


def record_delivery_failure(session_factory,row_id,alert_id,attempt,lease_token,error):
    """Atomically record FAILED-attempt metadata only for the current lease owner."""
    with session_factory() as session:
        session.add(AlertDeliveryRow(alert_id=alert_id,attempt=attempt,status="FAILED",error=str(error)[:1000]))
        if not Outbox(session).fail(row_id,lease_token,str(error)):
            session.rollback()
            return False
        # Outbox.fail commits the delivery audit row and retry/dead state together.
        return True


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
                    if not record_delivery_success(self.Session,row_id,alert_id,attempt,lease_token,response):
                        log.warning('Telegram accepted alert %s but lease ownership was lost before SENT commit; retry may duplicate delivery',alert_id)
                except Exception as exc:
                    log.exception('Telegram delivery failed or outcome is uncertain')
                    recorded=record_delivery_failure(self.Session,row_id,alert_id,attempt,lease_token,exc)
                    if not recorded:
                        log.warning('Could not record failed attempt for alert %s because lease ownership was lost',alert_id)
                    delay=getattr(exc,'retry_after',min(2**min(attempt,8),120))
                    await asyncio.sleep(min(max(float(delay),1),300))
        finally: await client.close()
