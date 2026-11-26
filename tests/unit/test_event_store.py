import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.connection import Base
from app.database.event_store import (
    AggregateVersionConflict,
    IdempotencyConflict,
    append_event,
)
from app.database.models import DomainEventRow


@pytest.fixture
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as value:
        yield value
    engine.dispose()


def append(session, *, version=1, key="event-key-1", payload=None):
    return append_event(
        session,
        aggregate_type="signal",
        aggregate_id="signal-123",
        aggregate_version=version,
        event_type="SignalObserved",
        payload=payload if payload is not None else {"direction": "CALL"},
        idempotency_key=key,
        source="unit-test",
    )


def test_append_event_persists_versioned_event(session):
    event = append(session)
    session.commit()
    stored = session.execute(
        select(DomainEventRow).where(DomainEventRow.event_id == event.event_id)
    ).scalar_one()
    assert stored.aggregate_type == "signal"
    assert stored.aggregate_id == "signal-123"
    assert stored.aggregate_version == 1
    assert stored.payload == {"direction": "CALL"}
    assert stored.schema_version == 1


def test_exact_idempotent_retry_returns_original_event(session):
    first = append(session)
    session.commit()
    retry = append(session)
    assert retry.event_id == first.event_id
    session.commit()
    assert session.execute(select(DomainEventRow)).scalars().all() == [first]


def test_reusing_idempotency_key_for_different_payload_fails(session):
    append(session)
    session.commit()
    with pytest.raises(IdempotencyConflict):
        append(session, payload={"direction": "PUT"})


def test_duplicate_aggregate_version_with_new_key_fails(session):
    append(session)
    session.commit()
    with pytest.raises(AggregateVersionConflict):
        append(session, key="event-key-2")


def test_aggregate_versions_are_scoped_by_aggregate(session):
    append(session)
    other = append_event(
        session,
        aggregate_type="trade",
        aggregate_id="signal-123",
        aggregate_version=1,
        event_type="TradeOpened",
        payload={"state": "OPEN"},
        idempotency_key="trade-event-1",
    )
    session.commit()
    assert other.aggregate_type == "trade"


def test_caller_rollback_removes_uncommitted_event(session):
    append(session)
    session.rollback()
    assert session.execute(select(DomainEventRow)).scalars().all() == []


def test_invalid_event_contract_is_rejected(session):
    with pytest.raises(ValueError):
        append_event(
            session,
            aggregate_type="signal",
            aggregate_id="signal-123",
            aggregate_version=0,
            event_type="SignalObserved",
            payload={},
            idempotency_key="bad-version",
        )
    with pytest.raises(ValueError):
        append_event(
            session,
            aggregate_type="signal",
            aggregate_id="signal-123",
            aggregate_version=True,
            event_type="SignalObserved",
            payload={},
            idempotency_key="bool-version",
        )
    with pytest.raises(TypeError):
        append_event(
            session,
            aggregate_type="signal",
            aggregate_id="signal-123",
            aggregate_version=1,
            event_type="SignalObserved",
            payload="not-json-object",
            idempotency_key="bad-payload",
        )
