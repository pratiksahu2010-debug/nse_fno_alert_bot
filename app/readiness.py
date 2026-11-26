def readiness_snapshot(engine, runtime, initializing=False, startup_error=None):
    """Return dependency-aware readiness without changing the legacy health contract."""
    database = False
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
        database = True
    except Exception:
        pass

    universe_count = 0
    if runtime is not None and getattr(runtime, "universe", None) is not None:
        universe_count = len(runtime.universe.instruments)

    feed_connected = bool(
        runtime is not None
        and getattr(runtime, "ws", None) is not None
        and runtime.ws.connected
    )
    runtime_running = bool(runtime is not None and runtime.running)

    checks = {
        "database": database,
        "runtime": runtime_running,
        "initialization_complete": not initializing and startup_error is None,
        "universe_loaded": universe_count > 0,
        "feed_connected": feed_connected,
    }
    reasons = [name for name, passed in checks.items() if not passed]

    return {
        "ready": not reasons,
        "checks": checks,
        "not_ready_reasons": reasons,
        "initializing": bool(initializing),
        "startup_error": startup_error,
        "universe_instruments": universe_count,
        "alert_only": True,
        "order_placement_enabled": False,
    }
