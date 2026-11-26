import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.connection import Base
from app.database.event_store import append_event
from app.database.replay import (
    EventSchemaVersionError,
    MissingUpcasterError,
    ReplayGapError,
    UnknownEventTypeError,
    replay_aggregate,
)
from app.database.snapshots import save_snapshot


@pytest.fixture
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as value:
        yield value
    engine.dispose()


def add_event(session, version, key, payload, schema_version=1, event_type="ValueSet"):
    return append_event(
        session,
        aggregate_type="account",
        aggregate_id="A-1",
        aggregate_version=version,
        event_type=event_type,
        payload=payload,
        idempotency_key=key,
        schema_version=schema_version,
    )


def reducer(state, payload):
    state.update(payload)
    return state


def test_replay_reconstructs_aggregate_from_genesis(session):
    add_event(session, 1, "e1", {"balance": 10})
    add_event(session, 2, "e2", {"balance": 25})
    session.commit()

    result = replay_aggregate(
        session,
        aggregate_type="account",
        aggregate_id="A-1",
        reducers={"ValueSet": reducer},
        initial_state={"balance": 0},
    )
    assert result.state == {"balance": 25}
    assert result.aggregate_version == 2
    assert result.replayed_event_count == 2
    assert result.snapshot_version == 0


def test_replay_uses_snapshot_then_applies_event_suffix(session):
    first = add_event(session, 1, "e1", {"balance": 10})
    save_snapshot(
        session,
        aggregate_type="account",
        aggregate_id="A-1",
        aggregate_version=1,
        state={"balance": 10},
        last_event_id=first.event_id,
    )
    add_event(session, 2, "e2", {"balance": 25})
    session.commit()

    result = replay_aggregate(
        session,
        aggregate_type="account",
        aggregate_id="A-1",
        reducers={"ValueSet": reducer},
    )
    assert result.state == {"balance": 25}
    assert result.aggregate_version == 2
    assert result.replayed_event_count == 1
    assert result.snapshot_version == 1


def test_replay_rejects_missing_aggregate_version(session):
    add_event(session, 1, "e1", {"balance": 10})
    add_event(session, 3, "e3", {"balance": 30})
    session.commit()

    with pytest.raises(ReplayGapError):
        replay_aggregate(
            session,
            aggregate_type="account",
            aggregate_id="A-1",
            reducers={"ValueSet": reducer},
        )


def test_replay_rejects_requested_version_beyond_history(session):
    add_event(session, 1, "e1", {"balance": 10})
    session.commit()
    with pytest.raises(ReplayGapError):
        replay_aggregate(
            session,
            aggregate_type="account",
            aggregate_id="A-1",
            reducers={"ValueSet": reducer},
            target_version=2,
        )


def test_replay_rejects_unknown_event_type(session):
    add_event(session, 1, "e1", {"balance": 10}, event_type="Unknown")
    session.commit()
    with pytest.raises(UnknownEventTypeError):
        replay_aggregate(
            session,
            aggregate_type="account",
            aggregate_id="A-1",
            reducers={"ValueSet": reducer},
        )


def test_replay_applies_explicit_schema_upcaster(session):
    add_event(session, 1, "e1", {"amount": 7}, schema_version=1)
    session.commit()

    result = replay_aggregate(
        session,
        aggregate_type="account",
        aggregate_id="A-1",
        reducers={"ValueSet": reducer},
        upcasters={("ValueSet", 1): lambda payload: {"balance": payload["amount"]}},
        target_schema_versions={"ValueSet": 2},
    )
    assert result.state == {"balance": 7}


def test_replay_requires_missing_upcaster_and_rejects_newer_schema(session):
    add_event(session, 1, "e1", {"amount": 7}, schema_version=1)
    session.commit()
    with pytest.raises(MissingUpcasterError):
        replay_aggregate(
            session,
            aggregate_type="account",
            aggregate_id="A-1",
            reducers={"ValueSet": reducer},
            target_schema_versions={"ValueSet": 2},
        )

    add_event(session, 2, "e2", {"balance": 8}, schema_version=3)
    session.commit()
    with pytest.raises(EventSchemaVersionError):
        replay_aggregate(
            session,
            aggregate_type="account",
            aggregate_id="A-1",
            reducers={"ValueSet": reducer},
            upcasters={("ValueSet", 1): lambda payload: payload},
            target_version=2,
            target_schema_versions={"ValueSet": 2},
        )


def test_replay_does_not_mutate_initial_state_or_event_payload(session):
    initial = {"balance": 0}
    payload = {"balance": 50}
    add_event(session, 1, "e1", payload)
    session.commit()

    replay_aggregate(
        session,
        aggregate_type="account",
        aggregate_id="A-1",
        reducers={"ValueSet": reducer},
        initial_state=initial,
    )
    assert initial == {"balance": 0}
    assert payload == {"balance": 50}
