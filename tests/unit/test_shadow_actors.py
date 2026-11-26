import asyncio
from types import SimpleNamespace
from datetime import datetime, timezone

from app.actors.shadow_runtime import ShadowActorRegistry
from app.market_data.models import Tick


def make_tick(key, second=0, price=100):
    return Tick(
        key,
        datetime(2026, 1, 1, 4, 0, second, tzinfo=timezone.utc),
        price,
        last_qty=1,
    )


def test_actor_mailbox_is_bounded_and_drops_without_blocking():
    async def scenario():
        registry = ShadowActorRegistry(mailbox_size=1, max_symbols=2)
        registry.start()

        assert registry.submit(make_tick("X", 0, 100)) is True
        # No event-loop yield yet: the one-slot mailbox is full.
        assert registry.submit(make_tick("X", 1, 101)) is False

        await registry.stop()
        snapshot = registry.snapshot()
        assert snapshot["actor_count"] == 1
        assert snapshot["processed"] == 1
        assert snapshot["dropped"] == 1
        assert snapshot["queue_depth"] == 0
        assert snapshot["enabled"] is False

    asyncio.run(scenario())


def test_registry_keeps_symbols_isolated_and_enforces_actor_limit():
    async def scenario():
        registry = ShadowActorRegistry(mailbox_size=4, max_symbols=1)
        registry.start()

        assert registry.submit(make_tick("X")) is True
        assert registry.submit(make_tick("Y")) is False
        await registry.stop()

        snapshot = registry.snapshot()
        assert snapshot["actor_count"] == 1
        assert snapshot["rejected_symbols"] == 1
        assert snapshot["actors"][0]["instrument_key"] == "X"

    asyncio.run(scenario())


def test_shadow_actor_stops_accepting_ticks_after_shutdown():
    async def scenario():
        registry = ShadowActorRegistry()
        registry.start()
        assert registry.submit(make_tick("X")) is True
        await registry.stop()
        assert registry.submit(make_tick("X", 2, 102)) is False

    asyncio.run(scenario())


def test_malformed_shadow_tick_does_not_kill_actor_or_block_shutdown():
    async def scenario():
        registry = ShadowActorRegistry(mailbox_size=4, max_symbols=1)
        registry.start()

        assert registry.submit(SimpleNamespace(instrument_key="X")) is True
        assert registry.submit(make_tick("X", 1, 101)) is True
        await registry.stop()

        snapshot = registry.snapshot()
        assert snapshot["processed"] == 1
        assert snapshot["failed"] == 1
        assert snapshot["last_error"] == "AttributeError"
        assert snapshot["queue_depth"] == 0

    asyncio.run(scenario())



def test_actor_shutdown_timeout_is_bounded_and_retryable():
    from app.actors.shadow_runtime import SymbolActor

    async def scenario():
        actor = SymbolActor("X", mailbox_size=2)
        release = asyncio.Event()

        async def delayed_consumer():
            item = await actor.mailbox.get()
            await release.wait()
            actor.mailbox.task_done()
            stop = await actor.mailbox.get()
            actor.mailbox.task_done()
            assert stop is not None

        actor._run = delayed_consumer
        actor.start()
        assert actor.submit(make_tick("X")) is True
        await asyncio.sleep(0)

        assert await actor.stop(timeout=0.01) is False
        assert actor.task is not None
        assert actor.accepting is False

        release.set()
        assert await actor.stop(timeout=1.0) is True
        assert actor.task is None
        assert actor.mailbox.empty()

    asyncio.run(scenario())


def test_registry_reports_actor_drain_timeout():
    from app.actors.shadow_runtime import SymbolActor

    async def scenario():
        registry = ShadowActorRegistry()
        actor = SymbolActor("X")
        registry.actors["X"] = actor
        registry.accepting = True
        release = asyncio.Event()

        async def delayed_consumer():
            await actor.mailbox.get()
            await release.wait()
            actor.mailbox.task_done()
            await actor.mailbox.get()
            actor.mailbox.task_done()

        actor._run = delayed_consumer
        actor.start()
        assert actor.submit(make_tick("X")) is True
        await asyncio.sleep(0)

        assert await registry.stop(timeout=0.01) is False
        assert registry.accepting is False
        release.set()
        assert await registry.stop(timeout=1.0) is True
        assert actor.task is None

    asyncio.run(scenario())
