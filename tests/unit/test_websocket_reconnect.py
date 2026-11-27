import asyncio
from types import SimpleNamespace

import pytest

from app.market_data.websocket_manager import WebsocketManager


class FakeSocket:
    def __init__(self, events, manager):
        self.events = events
        self.manager = manager
    async def send(self, payload):
        self.events.append("subscribe")
    def __aiter__(self):
        return self
    async def __anext__(self):
        self.manager.stop()
        raise StopAsyncIteration


class FakeConnect:
    def __init__(self, socket):
        self.socket = socket
    async def __aenter__(self):
        return self.socket
    async def __aexit__(self, *args):
        return False


@pytest.mark.asyncio
async def test_reconnect_callback_runs_before_socket_authorization_and_subscription(monkeypatch):
    events = []
    async def repair():
        events.append("repair")
    manager = WebsocketManager(
        client=None,
        keys=["NSE_EQ|X"],
        decoder=lambda payload: [],
        on_tick=lambda tick: None,
        before_connect=repair,
    )
    manager.running = True
    async def authorize():
        return {"data": {"authorized_redirect_uri": "wss://example.invalid"}}
    async def authorize_with_event():
        events.append('authorize')
        return await authorize()
    manager.client = SimpleNamespace(authorize_market_feed=authorize_with_event)
    socket = FakeSocket(events, manager)
    monkeypatch.setattr(
        "app.market_data.websocket_manager.websockets.connect",
        lambda *a, **k: FakeConnect(socket),
    )
    await manager.run()
    assert events[:3] == ["repair", "authorize", "subscribe"]


def test_new_socket_is_not_fresh_until_it_delivers_a_tick():
    manager = WebsocketManager(None, ["X"], lambda _: [], lambda _: None)
    manager.connected = True
    manager.last_tick_at = 100.0
    assert manager.feed_fresh(now=110.0) is True
    # A reconnect resets the tick timestamp before accepting frames.
    manager.last_tick_at = None
    assert manager.feed_fresh(now=110.0) is False


def test_feed_freshness_expires_after_configured_stale_window():
    manager = WebsocketManager(None, ["X"], lambda _: [], lambda _: None, stale_seconds=30)
    manager.connected = True
    manager.last_tick_at = 100.0
    assert manager.feed_fresh(now=129.9) is True
    assert manager.feed_fresh(now=130.1) is False


def test_disconnected_socket_is_never_fresh_even_after_recent_tick():
    manager = WebsocketManager(None, ["X"], lambda _: [], lambda _: None)
    manager.connected = False
    manager.last_tick_at = 100.0
    assert manager.feed_fresh(now=101.0) is False
