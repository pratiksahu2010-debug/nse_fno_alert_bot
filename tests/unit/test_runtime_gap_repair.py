from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.market_data.models import Candle
from app.runtime import LiveRuntime


class FakeClient:
    def __init__(self, responses=None, failures=None):
        self.responses = responses or {}
        self.failures = failures or {}
        self.calls = []

    async def intraday_candles(self, key, unit, interval):
        self.calls.append((key, unit, interval))
        if key in self.failures:
            raise RuntimeError("simulated REST outage")
        return {"data": {"candles": self.responses.get((key, interval), [])}}


def _row(ts, close=101):
    return [ts.isoformat(), 100, max(101, close), 99, close, 50]


def _runtime(client, keys):
    runtime = object.__new__(LiveRuntime)
    runtime._repair_lock = __import__("asyncio").Lock()
    runtime.client = client
    runtime.settings = SimpleNamespace(timezone="Asia/Kolkata")
    runtime.universe = SimpleNamespace(instruments=[{"instrument_key": key} for key in keys])
    runtime.hist = {}
    runtime.one_hist = {}
    runtime.repair_blocked_keys = set()
    return runtime


@pytest.mark.asyncio
async def test_reconnect_repair_backfills_completed_five_minute_bars_without_strategy_replay(monkeypatch):
    key = "NSE_EQ|TEST"
    start = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start -= timedelta(minutes=(start.minute % 5))
    # Use a recent regular-session timestamp in the test's exchange-local day.
    from zoneinfo import ZoneInfo
    local = datetime.now(ZoneInfo("Asia/Kolkata")).replace(hour=9, minute=15, second=0, microsecond=0)
    start = local.astimezone(timezone.utc)
    rows = [_row(start), _row(start + timedelta(minutes=5))]
    client = FakeClient({(key, 5): rows})
    runtime = _runtime(client, [key])
    runtime._repair_after_reconnect = LiveRuntime._repair_after_reconnect.__get__(runtime)
    await runtime._repair_after_reconnect(now=start + timedelta(minutes=10))
    expected = [start, start + timedelta(minutes=5)]
    assert [c.start for c in runtime.hist[key]] == expected
    assert runtime.hist[key][0].source == "historical"
    assert key not in runtime.repair_blocked_keys
    assert client.calls == [(key, "minutes", 5)]


@pytest.mark.asyncio
async def test_reconnect_failure_blocks_symbol_until_a_later_successful_repair():
    key = "NSE_EQ|BROKEN"
    runtime = _runtime(FakeClient(failures={key: True}), [key])
    await LiveRuntime._repair_after_reconnect(runtime)
    assert key in runtime.repair_blocked_keys


@pytest.mark.asyncio
async def test_reconnect_repairs_one_minute_history_when_microstructure_history_exists():
    key = "NSE_EQ|TEST"
    from zoneinfo import ZoneInfo
    local = datetime.now(ZoneInfo("Asia/Kolkata")).replace(hour=9, minute=15, second=0, microsecond=0)
    start = local.astimezone(timezone.utc)
    client = FakeClient({(key, 5): [], (key, 1): [_row(start)]})
    runtime = _runtime(client, [key])
    runtime.one_hist[key] = [Candle(key, start - timedelta(minutes=1), start, 99, 100, 98, 99, 10)]
    await LiveRuntime._repair_after_reconnect(runtime, now=start + timedelta(minutes=1))
    assert len(runtime.one_hist[key]) == 2
    assert client.calls == [(key, "minutes", 5), (key, "minutes", 1)]
