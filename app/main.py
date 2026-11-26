import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .config import Settings
from .logging_config import configure_logging
from .database.connection import Base, make_engine
from .runtime import LiveRuntime
from .market_data.universe_bootstrap import refresh_fno_universe
from .readiness import readiness_snapshot

settings = Settings()
configure_logging(settings.log_level)
log = logging.getLogger(__name__)
engine = make_engine(settings.database_url)
Base.metadata.create_all(engine)

runtime = None
startup_task = None
startup_error = None
initializing = False


async def initialize_runtime():
    global runtime, startup_error, initializing
    initializing = True
    startup_error = None
    candidate = None
    try:
        # Build and validate the complete reviewed stock universe before starting signals.
        snapshot = await refresh_fno_universe(
            settings.upstox_access_token,
            "config/fno_eligible_symbols.txt",
            settings.universe_path,
        )
        log.info(
            "Validated NSE F&O universe snapshot: %s (%d stocks + 2 indices)",
            snapshot["version"],
            snapshot["stock_count"],
        )
        candidate = LiveRuntime(settings, engine)
        await candidate.start()
        runtime = candidate
        log.info("Live alert runtime initialized successfully")
    except Exception as exc:
        startup_error = str(exc)
        log.exception("Live runtime initialization failed; health will report degraded state")
        if candidate is not None:
            try:
                await candidate.stop()
            except Exception:
                log.exception("Error stopping partially initialized runtime")
        runtime = None
    finally:
        initializing = False


@asynccontextmanager
async def lifespan(app):
    global startup_task, runtime
    # Bind the HTTP port immediately. Universe download and historical warm-up run in
    # the background so Render health checks do not wait on hundreds of broker requests.
    startup_task = asyncio.create_task(initialize_runtime(), name="runtime-initialization")
    yield
    if startup_task and not startup_task.done():
        startup_task.cancel()
        await asyncio.gather(startup_task, return_exceptions=True)
    if runtime:
        await runtime.stop()
        runtime = None


app = FastAPI(title="NSE F&O Alert Bot", version="2.2.0", lifespan=lifespan)


@app.get("/health")
async def health():
    db = False
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
        db = True
    except Exception:
        pass
    feed = bool(runtime and runtime.ws and runtime.ws.connected)
    stale = runtime.ws.stale_keys() if runtime and runtime.ws else []
    ready = bool(db and runtime is not None and feed)
    return {
        "ok": ready,
        "database": db,
        "runtime": runtime is not None,
        "initializing": initializing,
        "startup_error": startup_error,
        "feed_connected": feed,
        "stale_instruments": len(stale),
        "universe_version": runtime.universe.version if runtime else None,
        "universe_instruments": len(runtime.universe.instruments) if runtime else 0,
        "alert_only": True,
        "order_placement_enabled": False,
    }


@app.get("/ready")
def ready():
    snapshot = readiness_snapshot(engine, runtime, initializing, startup_error)
    return JSONResponse(
        status_code=200 if snapshot["ready"] else 503,
        content=snapshot,
    )


@app.get("/live")
def live():
    return {"live": True, "alert_only": True, "order_placement_enabled": False}


@app.get("/status")
async def status():
    return await health()


@app.get("/ping")
async def ping():
    return {"ok": True, "purpose": "keepalive_only"}


@app.get("/")
async def root():
    return {
        "service": "NSE F&O Signal Alert Bot",
        "strategies": ["ORB_GAP", "MOMENTUM_EXPLOSION"],
        "alert_only": True,
        "order_placement_enabled": False,
    }
