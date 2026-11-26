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
    universe_version = None
    universe_valid = False
    universe_error = None
    if runtime is not None and getattr(runtime, "universe", None) is not None:
        universe = runtime.universe
        universe_count = len(getattr(universe, "instruments", []))
        universe_version = getattr(universe, "version", None)
        try:
            universe.validate()
            universe_valid = True
        except Exception as exc:
            universe_error = str(exc)

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
        "universe_valid": universe_valid,
        "feed_connected": feed_connected,
    }
    reasons = [name for name, passed in checks.items() if not passed]

    return {
        "ready": not reasons,
        "checks": checks,
        "not_ready_reasons": reasons,
        "initializing": bool(initializing),
        "startup_error": startup_error,
        "universe_error": universe_error,
        "universe_version": universe_version,
        "universe_instruments": universe_count,
        "alert_only": True,
        "order_placement_enabled": False,
    }
