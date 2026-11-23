import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from .config import Settings
from .logging_config import configure_logging
from .database.connection import Base,make_engine
from .runtime import LiveRuntime
settings=Settings(); configure_logging(settings.log_level); log=logging.getLogger(__name__)
engine=make_engine(settings.database_url)
Base.metadata.create_all(engine)
runtime=None
@asynccontextmanager
async def lifespan(app):
    global runtime
    # Web process refuses silent fake-live mode: absent token or universe is reported unhealthy.
    try:
        runtime=LiveRuntime(settings,engine)
        await runtime.start()
    except Exception:
        log.exception('Live runtime did not start; health will report degraded state')
        runtime=None
    yield
    if runtime: await runtime.stop()
app=FastAPI(title='NSE F&O Alert Bot',version='2.0.0',lifespan=lifespan)
@app.get('/health')
async def health():
    db=False
    try:
        with engine.connect() as c:c.exec_driver_sql('SELECT 1')
        db=True
    except Exception: pass
    feed=bool(runtime and runtime.ws and runtime.ws.connected)
    stale=runtime.ws.stale_keys() if runtime and runtime.ws else []
    return {'ok':db and runtime is not None,'database':db,'runtime':runtime is not None,'feed_connected':feed,'stale_instruments':len(stale),'universe_version':runtime.universe.version if runtime else None,'alert_only':True,'order_placement_enabled':False}
@app.get('/status')
async def status(): return await health()
@app.get('/ping')
async def ping(): return {'ok':True,'purpose':'keepalive_only'}
@app.get('/')
async def root(): return {'service':'NSE F&O Signal Alert Bot','strategies':['ORB_GAP','MOMENTUM_EXPLOSION'],'alert_only':True}
