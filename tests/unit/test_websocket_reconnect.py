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
async def test_reconnect_callback_runs_before_subscription(monkeypatch):
    events = []
    async def repair():
        events.append("repair")
    manager = WebsocketManager(
        client=None,
        keys=["NSE_EQ|X"],
        decoder=lambda payload: [],
        on_tick=lambda tick: None,
        on_connect=repair,
    )
    manager.running = True
    async def authorize():
        return {"data": {"authorized_redirect_uri": "wss://example.invalid"}}
    manager.client = SimpleNamespace(authorize_market_feed=authorize)
    socket = FakeSocket(events, manager)
    monkeypatch.setattr(
        "app.market_data.websocket_manager.websockets.connect",
        lambda *a, **k: FakeConnect(socket),
    )
    await manager.run()
    assert events[:2] == ["repair", "subscribe"]
