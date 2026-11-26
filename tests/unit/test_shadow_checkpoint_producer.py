import asyncio
from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.actors.checkpoint_producer import ShadowCheckpointProducer
from app.actors.shadow_runtime import ShadowActorRegistry
from app.database.connection import Base
from app.database.models import DomainEventRow


def make_factory(tmp_path):
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'checkpoint-events.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return engine, factory


def snapshot(key="NSE_FO|NIFTY", price=24000.0, processed=1):
    return {
        "instrument_key": key,
        "last_timestamp": datetime.now(timezone.utc).isoformat(),
        "last_price": price,
        "processed": processed,
    }


def read_events(factory, key):
    with factory() as session:
        return session.scalars(
            select(DomainEventRow)
            .where(
                DomainEventRow.aggregate_type == "shadow_actor",
                DomainEventRow.aggregate_id == key,
            )
            .order_by(DomainEventRow.aggregate_version)
        ).all()


def test_checkpoint_producer_coalesces_latest_state_and_persists_event(tmp_path):
    engine, factory = make_factory(tmp_path)

    async def scenario():
        producer = ShadowCheckpointProducer(
            factory, max_pending_symbols=2, min_interval_seconds=0
        )
        producer.start()
        assert producer.submit(snapshot(price=24000, processed=1), force=True)
        assert producer.submit(snapshot(price=24010, processed=2), force=True)
        assert await producer.flush()
        assert await producer.stop()

    asyncio.run(scenario())
    rows = read_events(factory, "NSE_FO|NIFTY")
    assert len(rows) == 1
    assert rows[0].aggregate_version == 1
    assert rows[0].event_type == "ObservationCheckpointed"
    assert rows[0].payload["last_price"] == 24010.0
    assert rows[0].payload["processed"] == 2
    engine.dispose()


def test_checkpoint_producer_advances_versions_sequentially(tmp_path):
    engine, factory = make_factory(tmp_path)

    async def scenario():
        producer = ShadowCheckpointProducer(factory, min_interval_seconds=0)
        producer.start()
        assert producer.submit(snapshot(price=100, processed=1), force=True)
        assert await producer.flush()
        assert producer.submit(snapshot(price=101, processed=2), force=True)
        assert await producer.flush()
        assert await producer.stop()

    asyncio.run(scenario())
    rows = read_events(factory, "NSE_FO|NIFTY")
    assert [row.aggregate_version for row in rows] == [1, 2]
    assert rows[-1].payload["last_price"] == 101.0
    engine.dispose()


def test_producer_throttles_without_blocking_submit(tmp_path):
    engine, factory = make_factory(tmp_path)

    async def scenario():
        producer = ShadowCheckpointProducer(factory, min_interval_seconds=60)
        producer.start()
        assert producer.submit(snapshot(), force=True)
        assert producer.submit(snapshot(price=24001), force=False) is False
        assert producer.throttled == 1
        assert await producer.stop()

    asyncio.run(scenario())
    assert len(read_events(factory, "NSE_FO|NIFTY")) == 1
    engine.dispose()


def test_shadow_actor_registry_can_feed_optional_checkpoint_sink(tmp_path):
    engine, factory = make_factory(tmp_path)
    producer = ShadowCheckpointProducer(factory, min_interval_seconds=0)

    async def scenario():
        producer.start()
        registry = ShadowActorRegistry(
            max_symbols=2, checkpoint_sink=producer.submit
        )
        registry.start()
        tick = type(
            "Tick",
            (),
            {
                "instrument_key": "NSE_FO|BANKNIFTY",
                "timestamp": datetime.now(timezone.utc),
                "price": 52000.0,
            },
        )()
        assert registry.submit(tick)
        # Let the actor consume the tick and enqueue its checkpoint.
        await asyncio.sleep(0)
        assert await producer.flush()
        await registry.stop()
        assert await producer.stop()

    asyncio.run(scenario())
    rows = read_events(factory, "NSE_FO|BANKNIFTY")
    assert len(rows) == 1
    assert rows[0].payload["last_price"] == 52000.0
    engine.dispose()


def test_new_producer_loads_existing_version_and_first_submit_is_not_throttled(tmp_path):
    engine, factory = make_factory(tmp_path)

    async def scenario():
        first = ShadowCheckpointProducer(factory, min_interval_seconds=60)
        first.start()
        assert first.submit(snapshot(price=100, processed=1))
        assert await first.flush()
        assert await first.stop()

        restarted = ShadowCheckpointProducer(factory, min_interval_seconds=60)
        restarted.start()
        assert restarted.submit(snapshot(price=101, processed=2))
        assert await restarted.flush()
        assert await restarted.stop()

    asyncio.run(scenario())
    rows = read_events(factory, "NSE_FO|NIFTY")
    assert [row.aggregate_version for row in rows] == [1, 2]
    assert rows[-1].payload["last_price"] == 101.0
    engine.dispose()


def test_invalid_checkpoint_is_rejected_before_queueing(tmp_path):
    engine, factory = make_factory(tmp_path)

    async def scenario():
        producer = ShadowCheckpointProducer(factory)
        producer.start()
        invalid = snapshot()
        invalid["last_price"] = float("nan")
        assert producer.submit(invalid) is False
        assert producer.failed == 1
        assert await producer.stop()

    asyncio.run(scenario())
    assert read_events(factory, "NSE_FO|NIFTY") == []
    engine.dispose()
