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


class FakeUniverse:
    instruments = ["X"]
    version = "TEST"

    def __init__(self, valid=True):
        self.valid = valid

    def validate(self):
        if not self.valid:
            raise ValueError("incomplete F&O universe")
        return True


class FakeFeed:
    stale_seconds = 90
    received_ticks = 1

    def __init__(self, connected=True, fresh=True):
        self.connected = connected
        self.fresh = fresh

    def feed_fresh(self):
        return self.connected and self.fresh

    def tick_age_seconds(self):
        return 0.0 if self.fresh else 120.0


class FakeRuntime:
    def __init__(self, connected=True, running=True, universe_valid=True, feed_fresh=True):
        self.running = running
        self.ws = FakeFeed(connected, feed_fresh)
        self.universe = FakeUniverse(universe_valid)


def test_readiness_passes_when_all_required_dependencies_are_ready():
    result = readiness_snapshot(FakeEngine(), FakeRuntime())

    assert result["ready"] is True
    assert result["not_ready_reasons"] == []
    assert result["checks"] == {
        "database": True,
        "runtime": True,
        "initialization_complete": True,
        "universe_valid": True,
        "feed_connected": True,
        "feed_fresh": True,
    }
    assert result["feed_tick_age_seconds"] == 0.0
    assert result["alert_only"] is True
    assert result["order_placement_enabled"] is False


def test_readiness_fails_when_feed_is_disconnected():
    result = readiness_snapshot(FakeEngine(), FakeRuntime(connected=False))

    assert result["ready"] is False
    assert "feed_connected" in result["not_ready_reasons"]
    assert "feed_fresh" in result["not_ready_reasons"]


def test_readiness_fails_when_connected_feed_is_stale():
    result = readiness_snapshot(FakeEngine(), FakeRuntime(feed_fresh=False))

    assert result["ready"] is False
    assert "feed_connected" not in result["not_ready_reasons"]
    assert "feed_fresh" in result["not_ready_reasons"]
    assert result["feed_tick_age_seconds"] == 120.0


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
    no_universe = readiness_snapshot(
        FakeEngine(), FakeRuntime(universe_valid=False)
    )

    assert no_database["ready"] is False
    assert "database" in no_database["not_ready_reasons"]
    assert no_universe["ready"] is False
    assert "universe_valid" in no_universe["not_ready_reasons"]
    assert no_universe["universe_error"] == "incomplete F&O universe"


def test_readiness_fails_when_runtime_is_not_running():
    result = readiness_snapshot(FakeEngine(), FakeRuntime(running=False))

    assert result["ready"] is False
    assert "runtime" in result["not_ready_reasons"]
