import asyncio
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.actors.session import ShadowActorSession, ShadowSessionState
from app.database.connection import Base
from app.database.event_store import append_event
from app.database.models import DomainEventRow


@pytest.fixture
def session_factory(tmp_path):
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'shadow-session.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    engine.dispose()


def add_checkpoint(factory, key, *, price=100.0):
    with factory() as session:
        append_event(
            session,
            aggregate_type="shadow_actor",
            aggregate_id=key,
            aggregate_version=1,
            event_type="ObservationCheckpointed",
            schema_version=1,
            payload={
                "last_timestamp": "2026-11-26T10:15:00+05:30",
                "last_price": price,
                "processed": 1,
            },
            idempotency_key=f"seed:{key}:1",
            source="test",
        )
        session.commit()


def events(factory, key):
    with factory() as session:
        return session.scalars(
            select(DomainEventRow)
            .where(
                DomainEventRow.aggregate_type == "shadow_actor",
                DomainEventRow.aggregate_id == key,
            )
            .order_by(DomainEventRow.aggregate_version)
        ).all()


def test_session_recovers_before_start_and_flushes_final_checkpoint(session_factory):
    key = "NSE_FO|NIFTY"
    add_checkpoint(session_factory, key)
    session = ShadowActorSession(
        session_factory,
        [key],
        max_symbols=4,
        checkpoint_interval_seconds=0,
        min_persist_interval_seconds=0,
    )

    async def scenario():
        report = await session.start()
        assert report.restored == 1
        assert session.state == ShadowSessionState.READY
        actor = session.registry.actors[key]
        assert actor.task is not None
        tick = type(
            "Tick",
            (),
            {
                "instrument_key": key,
                "timestamp": datetime.now(timezone.utc),
                "price": 101.5,
            },
        )()
        assert session.submit(tick)
        assert await session.stop()
        assert session.state == ShadowSessionState.STOPPED

    asyncio.run(scenario())
    rows = events(session_factory, key)
    assert [row.aggregate_version for row in rows] == [1, 2, 3]
    assert rows[-1].payload["last_price"] == 101.5


def test_session_rejects_tick_before_explicit_start(session_factory):
    session = ShadowActorSession(session_factory, ["NSE_FO|NIFTY"])

    tick = type(
        "Tick",
        (),
        {
            "instrument_key": "NSE_FO|NIFTY",
            "timestamp": datetime.now(timezone.utc),
            "price": 100.0,
        },
    )()
    assert session.submit(tick) is False
    assert session.registry.actors == {}


def test_recovery_failure_does_not_start_any_actor(session_factory):
    key = "NSE_FO|BROKEN"
    with session_factory() as db:
        append_event(
            db,
            aggregate_type="shadow_actor",
            aggregate_id=key,
            aggregate_version=1,
            event_type="ObservationCheckpointed",
            payload={
                "last_timestamp": "not-a-timestamp",
                "last_price": 100.0,
                "processed": 1,
            },
            idempotency_key="broken:1",
            source="test",
        )
        db.commit()

    session = ShadowActorSession(session_factory, [key], max_symbols=2)

    with pytest.raises(Exception):
        asyncio.run(session.start())

    assert session.state == ShadowSessionState.FAILED
    assert session.registry.accepting is False
    assert all(actor.task is None for actor in session.registry.actors.values())
