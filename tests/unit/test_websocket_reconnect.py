import asyncio

import pytest

from app.market_data.websocket_manager import WebsocketManager


class FakeSocket:
    def __init__(self, events):
        self.events = events
    async def send(self, payload):
        self.events.append("subscribe")


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
    manager.client = type("Client", (), {"authorize_market_feed": authorize})()
    socket = FakeSocket(events)
    monkeypatch.setattr("app.market_data.websocket_manager.websockets.connect", lambda *a, **k: FakeConnect(socket))
    async def stop_after_subscribe():
        await asyncio.sleep(0)
        manager.stop()
        raise RuntimeError("end test connection")
    async def fake_iter():
        await stop_after_subscribe()
        if False:
            yield b""
    socket.__aiter__ = lambda self: fake_iter()
    await manager.run()
    assert events[:2] == ["repair", "subscribe"]
