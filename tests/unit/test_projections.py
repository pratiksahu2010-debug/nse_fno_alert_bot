import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.connection import Base
from app.database.event_store import append_event
from app.database.projections import (
    ProjectionAnchorError,
    ProjectionConflict,
    load_projection,
    save_projection,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as value:
        yield value
    engine.dispose()


def add_event(session, version, key, payload):
    return append_event(
        session,
        aggregate_type="order-book",
        aggregate_id="XYZ",
        aggregate_version=version,
        event_type="BookUpdated",
        payload=payload,
        idempotency_key=key,
    )


def test_projection_insert_and_update_with_expected_version(session):
    e1 = add_event(session, 1, "e1", {"bids": 1})
    first = save_projection(
        session,
        aggregate_type="order-book",
        aggregate_id="XYZ",
        aggregate_version=1,
        state={"bids": 1},
        last_event_id=e1.event_id,
    )
    session.commit()
    assert first.aggregate_version == 1

    e2 = add_event(session, 2, "e2", {"bids": 2})
    updated = save_projection(
        session,
        aggregate_type="order-book",
        aggregate_id="XYZ",
        aggregate_version=2,
        expected_current_version=1,
        state={"bids": 2},
        last_event_id=e2.event_id,
    )
    session.commit()
    assert updated.aggregate_version == 2
    assert load_projection(session, aggregate_type="order-book", aggregate_id="XYZ").state == {"bids": 2}


def test_projection_rejects_stale_writer(session):
    e1 = add_event(session, 1, "e1", {"bids": 1})
    save_projection(
        session,
        aggregate_type="order-book",
        aggregate_id="XYZ",
        aggregate_version=1,
        state={"bids": 1},
        last_event_id=e1.event_id,
    )
    session.commit()
    e2 = add_event(session, 2, "e2", {"bids": 2})
    save_projection(
        session,
        aggregate_type="order-book",
        aggregate_id="XYZ",
        aggregate_version=2,
        expected_current_version=1,
        state={"bids": 2},
        last_event_id=e2.event_id,
    )
    session.commit()

    e3 = add_event(session, 3, "e3", {"bids": 3})
    with pytest.raises(ProjectionConflict):
        save_projection(
            session,
            aggregate_type="order-book",
            aggregate_id="XYZ",
            aggregate_version=3,
            expected_current_version=1,
            state={"bids": 3},
            last_event_id=e3.event_id,
        )


def test_projection_retry_is_idempotent(session):
    event = add_event(session, 1, "e1", {"bids": 1})
    first = save_projection(
        session,
        aggregate_type="order-book",
        aggregate_id="XYZ",
        aggregate_version=1,
        state={"bids": 1},
        last_event_id=event.event_id,
    )
    session.commit()
    retry = save_projection(
        session,
        aggregate_type="order-book",
        aggregate_id="XYZ",
        aggregate_version=1,
        state={"bids": 1},
        last_event_id=event.event_id,
    )
    assert retry.aggregate_version == first.aggregate_version


def test_projection_rejects_same_version_different_state(session):
    event = add_event(session, 1, "e1", {"bids": 1})
    save_projection(
        session,
        aggregate_type="order-book",
        aggregate_id="XYZ",
        aggregate_version=1,
        state={"bids": 1},
        last_event_id=event.event_id,
    )
    session.commit()
    with pytest.raises(ProjectionConflict):
        save_projection(
            session,
            aggregate_type="order-book",
            aggregate_id="XYZ",
            aggregate_version=1,
            state={"bids": 100},
            last_event_id=event.event_id,
        )


def test_projection_rejects_mismatched_event_anchor(session):
    event = add_event(session, 1, "e1", {"bids": 1})
    with pytest.raises(ProjectionAnchorError):
        save_projection(
            session,
            aggregate_type="other",
            aggregate_id="XYZ",
            aggregate_version=1,
            state={"bids": 1},
            last_event_id=event.event_id,
        )


def test_projection_rollback_is_owned_by_caller(session):
    event = add_event(session, 1, "e1", {"bids": 1})
    session.commit()
    save_projection(
        session,
        aggregate_type="order-book",
        aggregate_id="XYZ",
        aggregate_version=1,
        state={"bids": 1},
        last_event_id=event.event_id,
    )
    session.rollback()
    assert load_projection(session, aggregate_type="order-book", aggregate_id="XYZ") is None
