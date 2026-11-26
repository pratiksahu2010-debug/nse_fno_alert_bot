import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.connection import Base
from app.database.event_store import append_event
from app.database.models import AggregateSnapshotRow
from app.database.snapshots import (
    SnapshotAnchorError,
    SnapshotConflict,
    SnapshotIntegrityError,
    load_latest_snapshot,
    save_snapshot,
    snapshot_checksum,
    verify_snapshot_checksum,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as value:
        yield value
    engine.dispose()


def add_event(session, version, key):
    return append_event(
        session,
        aggregate_type="signal",
        aggregate_id="signal-1",
        aggregate_version=version,
        event_type="SignalUpdated",
        payload={"state": "ACTIVE", "version": version},
        idempotency_key=key,
    )


def test_snapshot_checksum_is_stable_across_dictionary_key_order():
    assert snapshot_checksum({"a": 1, "b": 2}) == snapshot_checksum({"b": 2, "a": 1})


def test_snapshot_checksum_rejects_non_finite_json_values():
    with pytest.raises(ValueError, match="finite JSON"):
        snapshot_checksum({"price": float("nan")})


def test_snapshot_is_anchored_persisted_and_verified(session):
    event = add_event(session, 1, "event-1")
    snapshot = save_snapshot(
        session, aggregate_type="signal", aggregate_id="signal-1",
        aggregate_version=1, state={"status": "ACTIVE"}, last_event_id=event.event_id,
    )
    session.commit()
    stored = session.execute(
        select(AggregateSnapshotRow).where(AggregateSnapshotRow.snapshot_id == snapshot.snapshot_id)
    ).scalar_one()
    assert stored.state == {"status": "ACTIVE"}
    assert stored.last_event_id == event.event_id
    assert len(verify_snapshot_checksum(session, stored)) == 64


def test_snapshot_rejects_unknown_or_mismatched_anchor(session):
    with pytest.raises(SnapshotAnchorError):
        save_snapshot(
            session, aggregate_type="signal", aggregate_id="signal-1",
            aggregate_version=1, state={"status": "ACTIVE"}, last_event_id="missing-event",
        )
    event = add_event(session, 1, "event-1")
    with pytest.raises(SnapshotAnchorError):
        save_snapshot(
            session, aggregate_type="trade", aggregate_id="signal-1",
            aggregate_version=1, state={}, last_event_id=event.event_id,
        )
    with pytest.raises(SnapshotAnchorError):
        save_snapshot(
            session, aggregate_type="signal", aggregate_id="signal-1",
            aggregate_version=2, state={}, last_event_id=event.event_id,
        )


def test_exact_snapshot_retry_returns_existing_row(session):
    event = add_event(session, 1, "event-1")
    first = save_snapshot(
        session, aggregate_type="signal", aggregate_id="signal-1",
        aggregate_version=1, state={"status": "ACTIVE"}, last_event_id=event.event_id,
    )
    session.commit()
    retry = save_snapshot(
        session, aggregate_type="signal", aggregate_id="signal-1",
        aggregate_version=1, state={"status": "ACTIVE"}, last_event_id=event.event_id,
    )
    assert retry.snapshot_id == first.snapshot_id


def test_different_snapshot_at_same_version_conflicts(session):
    event = add_event(session, 1, "event-1")
    save_snapshot(
        session, aggregate_type="signal", aggregate_id="signal-1",
        aggregate_version=1, state={"status": "ACTIVE"}, last_event_id=event.event_id,
    )
    session.commit()
    with pytest.raises(SnapshotConflict):
        save_snapshot(
            session, aggregate_type="signal", aggregate_id="signal-1",
            aggregate_version=1, state={"status": "CLOSED"}, last_event_id=event.event_id,
        )


def test_load_latest_snapshot_can_be_bounded_by_event_version(session):
    event1 = add_event(session, 1, "event-1")
    event2 = add_event(session, 2, "event-2")
    save_snapshot(
        session, aggregate_type="signal", aggregate_id="signal-1",
        aggregate_version=1, state={"version": 1}, last_event_id=event1.event_id,
    )
    save_snapshot(
        session, aggregate_type="signal", aggregate_id="signal-1",
        aggregate_version=2, state={"version": 2}, last_event_id=event2.event_id,
    )
    session.commit()
    latest = load_latest_snapshot(session, aggregate_type="signal", aggregate_id="signal-1")
    bounded = load_latest_snapshot(
        session, aggregate_type="signal", aggregate_id="signal-1", max_version=1
    )
    assert latest.aggregate_version == 2
    assert bounded.aggregate_version == 1


def test_snapshot_rollback_is_owned_by_caller(session):
    event = add_event(session, 1, "event-1")
    session.commit()
    save_snapshot(
        session, aggregate_type="signal", aggregate_id="signal-1",
        aggregate_version=1, state={"status": "ACTIVE"}, last_event_id=event.event_id,
    )
    session.rollback()
    assert session.execute(select(AggregateSnapshotRow)).scalars().all() == []


def test_snapshot_state_tampering_is_detected(session):
    event = add_event(session, 1, "event-1")
    snapshot = save_snapshot(
        session, aggregate_type="signal", aggregate_id="signal-1",
        aggregate_version=1, state={"status": "ACTIVE"}, last_event_id=event.event_id,
    )
    session.commit()
    snapshot.state = {"status": "CORRUPTED"}
    session.commit()
    with pytest.raises(SnapshotIntegrityError, match="checksum mismatch"):
        verify_snapshot_checksum(session, snapshot)
