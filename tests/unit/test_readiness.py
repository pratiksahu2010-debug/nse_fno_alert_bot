from app.readiness import readiness_snapshot


class FakeConnection:
    def exec_driver_sql(self, statement):
        assert statement == "SELECT 1"


class FakeEngine:
    def __init__(self, fails=False):
        self.fails = fails

    def connect(self):
        if self.fails:
            raise RuntimeError("database unavailable")
        return self

    def __enter__(self):
        return FakeConnection()

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeRuntime:
    def __init__(self, connected=True, running=True, instruments=None):
        self.running = running
        self.ws = type("Feed", (), {"connected": connected})()
        self.universe = type(
            "Universe", (), {"instruments": instruments if instruments is not None else ["X"]}
        )()


def test_readiness_passes_when_all_required_dependencies_are_ready():
    result = readiness_snapshot(FakeEngine(), FakeRuntime())

    assert result["ready"] is True
    assert result["not_ready_reasons"] == []
    assert result["checks"] == {
        "database": True,
        "runtime": True,
        "initialization_complete": True,
        "universe_loaded": True,
        "feed_connected": True,
    }
    assert result["alert_only"] is True
    assert result["order_placement_enabled"] is False


def test_readiness_fails_when_feed_is_disconnected():
    result = readiness_snapshot(FakeEngine(), FakeRuntime(connected=False))

    assert result["ready"] is False
    assert "feed_connected" in result["not_ready_reasons"]


def test_readiness_fails_during_initialization_or_after_startup_error():
    initializing = readiness_snapshot(
        FakeEngine(), FakeRuntime(), initializing=True
    )
    failed = readiness_snapshot(
        FakeEngine(), None, startup_error="market data authorization failed"
    )

    assert initializing["ready"] is False
    assert "initialization_complete" in initializing["not_ready_reasons"]
    assert failed["ready"] is False
    assert "initialization_complete" in failed["not_ready_reasons"]
    assert failed["startup_error"] == "market data authorization failed"


def test_readiness_fails_when_database_or_universe_is_unavailable():
    no_database = readiness_snapshot(FakeEngine(fails=True), FakeRuntime())
    no_universe = readiness_snapshot(FakeEngine(), FakeRuntime(instruments=[]))

    assert no_database["ready"] is False
    assert "database" in no_database["not_ready_reasons"]
    assert no_universe["ready"] is False
    assert "universe_loaded" in no_universe["not_ready_reasons"]
