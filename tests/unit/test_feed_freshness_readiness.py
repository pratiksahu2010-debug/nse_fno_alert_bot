from types import SimpleNamespace

from app.readiness import readiness_snapshot


class FakeConnection:
    def exec_driver_sql(self, query):
        assert query == "SELECT 1"


class FakeEngine:
    def connect(self):
        return FakeContext()


class FakeContext:
    def __enter__(self):
        return FakeConnection()
    def __exit__(self, *args):
        return False


class FakeUniverse:
    instruments = [{"instrument_key": "X"}]
    version = "test"
    def validate(self):
        return True


def runtime_with_feed(fresh):
    ws = SimpleNamespace(
        connected=True,
        stale_seconds=90,
        received_ticks=3,
        feed_fresh=lambda: fresh,
        tick_age_seconds=lambda: 2.0 if fresh else 120.0,
    )
    return SimpleNamespace(universe=FakeUniverse(), ws=ws, running=True)


def test_readiness_requires_recent_feed_tick_not_just_connected_socket():
    snapshot = readiness_snapshot(FakeEngine(), runtime_with_feed(False))
    assert snapshot["checks"]["feed_connected"] is True
    assert snapshot["checks"]["feed_fresh"] is False
    assert snapshot["ready"] is False
    assert "feed_fresh" in snapshot["not_ready_reasons"]


def test_readiness_accepts_connected_socket_with_recent_feed_tick():
    snapshot = readiness_snapshot(FakeEngine(), runtime_with_feed(True))
    assert snapshot["ready"] is True
    assert snapshot["checks"]["feed_fresh"] is True
    assert snapshot["feed_tick_age_seconds"] == 2.0


def test_readiness_fails_if_socket_is_disconnected_even_if_tick_was_recent():
    runtime = runtime_with_feed(True)
    runtime.ws.connected = False
    snapshot = readiness_snapshot(FakeEngine(), runtime)
    assert snapshot["ready"] is False
    assert snapshot["checks"]["feed_fresh"] is False
