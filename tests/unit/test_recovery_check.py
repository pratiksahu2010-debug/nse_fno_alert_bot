import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.connection import Base
from app.database.event_store import append_event
from app.database.models import AggregateProjectionRow
from app.database.projections import save_projection
from app.database.recovery_check import audit_projection


@pytest.fixture
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as value:
        yield value
    engine.dispose()


def add_event(session, version, value):
    return append_event(
        session,
        aggregate_type="portfolio",
        aggregate_id="P-1",
        aggregate_version=version,
        event_type="ValueSet",
        payload={"value": value},
        idempotency_key=f"event-{version}",
    )


def reducer(state, payload):
    state.update(payload)
    return state


def save_view(session, event, version, state):
    return save_projection(
        session,
        aggregate_type="portfolio",
        aggregate_id="P-1",
        aggregate_version=version,
        state=state,
        last_event_id=event.event_id,
        expected_current_version=0,
    )


def audit(session):
    return audit_projection(
        session,
        aggregate_type="portfolio",
        aggregate_id="P-1",
        reducers={"ValueSet": reducer},
        initial_state={"value": 0},
    )


def test_empty_aggregate_is_consistent(session):
    result = audit(session)
    assert result.ok is True
    assert result.status == "EMPTY"


def test_projection_matches_replay(session):
    first = add_event(session, 1, 10)
    second = add_event(session, 2, 25)
    save_view(session, second, 2, {"value": 25})
    session.commit()

    result = audit(session)
    assert result.ok is True
    assert result.status == "MATCH"
    assert result.projection_version == result.latest_event_version == 2
    assert result.replayed_event_count == 2


def test_missing_projection_is_reported(session):
    add_event(session, 1, 10)
    session.commit()
    result = audit(session)
    assert result.ok is False
    assert result.status == "PROJECTION_MISSING"


def test_stale_projection_is_distinguished_from_state_drift(session):
    first = add_event(session, 1, 10)
    add_event(session, 2, 25)
    save_view(session, first, 1, {"value": 10})
    session.commit()

    result = audit(session)
    assert result.ok is False
    assert result.status == "PROJECTION_STALE"
    assert result.replayed_event_count == 1


def test_projection_state_drift_is_detected(session):
    first = add_event(session, 1, 10)
    save_view(session, first, 1, {"value": 999})
    session.commit()
    result = audit(session)
    assert result.ok is False
    assert result.status == "STATE_MISMATCH"


def test_projection_anchor_drift_is_detected(session):
    first = add_event(session, 1, 10)
    save_view(session, first, 1, {"value": 10})
    session.commit()
    projection = session.get(AggregateProjectionRow, ("portfolio", "P-1"))
    projection.last_event_id = "not-the-event"
    session.commit()

    result = audit(session)
    assert result.ok is False
    assert result.status == "ANCHOR_MISMATCH"


def test_projection_ahead_of_event_ledger_is_detected(session):
    projection = AggregateProjectionRow(
        aggregate_type="portfolio",
        aggregate_id="P-1",
        aggregate_version=1,
        state={"value": 10},
        last_event_id="not-yet-in-ledger",
    )
    session.add(projection)
    session.commit()

    result = audit(session)
    assert result.ok is False
    assert result.status == "PROJECTION_AHEAD"


def test_audit_does_not_modify_projection_or_event_rows(session):
    event = add_event(session, 1, 10)
    save_view(session, event, 1, {"value": 10})
    session.commit()
    before_id = session.get(AggregateProjectionRow, ("portfolio", "P-1")).last_event_id
    result = audit(session)
    after_id = session.get(AggregateProjectionRow, ("portfolio", "P-1")).last_event_id
    assert result.ok is True
    assert before_id == after_id == event.event_id
