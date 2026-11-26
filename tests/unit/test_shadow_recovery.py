import asyncio
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.actors.recovery import (
    RecoveryLifecycle,
    ShadowRecoveryCoordinator,
    ShadowRecoveryError,
)
from app.actors.shadow_runtime import ShadowActorRegistry
from app.database.connection import Base
from app.database.event_store import append_event
from app.database.snapshots import SnapshotChecksumRow, save_snapshot


def reducer(state, payload):
    state.update(payload)
    return state


@pytest.fixture
def session_factory(tmp_path):
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'shadow-recovery.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    engine.dispose()


def add_event(factory, key, payload, version=1):
    with factory() as session:
        event = append_event(
            session,
            aggregate_type="shadow_actor",
            aggregate_id=key,
            aggregate_version=version,
            event_type="ObservationCheckpointed",
            payload=payload,
            idempotency_key=f"{key}-{version}",
        )
        session.commit()
        return event.event_id


def coordinator(factory, registry, **kwargs):
    return ShadowRecoveryCoordinator(
        factory,
        registry,
        reducers={"ObservationCheckpointed": reducer},
        **kwargs,
    )


def test_recovers_verified_event_state_without_starting_actor_tasks(session_factory):
    key = "NSE_FO|NIFTY"
    stamp = "2026-11-26T10:15:00+05:30"
    add_event(session_factory, key, {
        "last_timestamp": stamp, "last_price": 24100.5, "processed": 17
    })
    registry = ShadowActorRegistry(mailbox_size=8, max_symbols=2)
    recovery = coordinator(session_factory, registry)

    report = asyncio.run(recovery.recover([key]))

    assert report.state == RecoveryLifecycle.READY
    assert report.restored == 1
    actor = registry.actors[key]
    assert actor.task is None
    assert actor.last_timestamp.isoformat() == stamp
    assert actor.last_price == 24100.5
    assert actor.processed == 17
    assert asyncio.run(recovery.stop()) is True
    assert recovery.state == RecoveryLifecycle.STOPPED


def test_missing_event_history_is_skipped(session_factory):
    registry = ShadowActorRegistry(max_symbols=2)
    recovery = coordinator(session_factory, registry)

    report = asyncio.run(recovery.recover(["EMPTY-SYMBOL"]))

    assert report.restored == 0
    assert report.skipped == 1
    assert registry.actors == {}


def test_invalid_checkpoint_fails_without_partial_registry_mutation(session_factory):
    add_event(session_factory, "GOOD", {
        "last_timestamp": "2026-11-26T10:15:00+05:30",
        "last_price": 100.0,
        "processed": 1,
    })
    add_event(session_factory, "BAD", {
        "last_timestamp": "not-a-date", "last_price": 200.0, "processed": 2
    })
    registry = ShadowActorRegistry(max_symbols=4)
    recovery = coordinator(session_factory, registry)

    with pytest.raises(ShadowRecoveryError, match="invalid last_timestamp"):
        asyncio.run(recovery.recover(["GOOD", "BAD"]))

    assert recovery.state == RecoveryLifecycle.FAILED
    assert registry.actors == {}


def test_snapshot_checksum_mismatch_fails_closed(session_factory):
    key = "NSE_FO|BANKNIFTY"
    state = {
        "last_timestamp": "2026-11-26T10:15:00+05:30",
        "last_price": 52000.0,
        "processed": 3,
    }
    event_id = add_event(session_factory, key, state)
    with session_factory() as session:
        snapshot = save_snapshot(
            session,
            aggregate_type="shadow_actor",
            aggregate_id=key,
            aggregate_version=1,
            state=state,
            last_event_id=event_id,
        )
        checksum = session.get(SnapshotChecksumRow, snapshot.snapshot_id)
        checksum.checksum = "0" * 64
        session.commit()

    registry = ShadowActorRegistry(max_symbols=2)
    recovery = coordinator(session_factory, registry)
    with pytest.raises(Exception, match="checksum mismatch"):
        asyncio.run(recovery.recover([key]))

    assert recovery.state == RecoveryLifecycle.FAILED
    assert registry.actors == {}


def test_registry_starts_restored_actor_only_after_explicit_start():
    registry = ShadowActorRegistry(max_symbols=1)
    registry.restore_checkpoints({
        "RESTORED": {
            "last_timestamp": datetime(2026, 11, 26, 10, 15, tzinfo=timezone.utc),
            "last_price": 10.0,
            "processed": 4,
        }
    })
    assert registry.actors["RESTORED"].task is None
    registry.start()
    assert registry.actors["RESTORED"].task is not None
    asyncio.run(registry.stop())
