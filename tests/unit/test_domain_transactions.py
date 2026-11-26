import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.connection import Base
from app.database.domain_outbox import DomainOutboxConflict
from app.database.models import AggregateProjectionRow, DomainEventRow, DomainOutboxRow
from app.database.projections import ProjectionConflict
from app.database.transactions import append_event_with_projection_and_outbox


@pytest.fixture
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as value:
        yield value
    engine.dispose()


def write(session, version=1, event_payload=None, projection_state=None, outbox_payload=None):
    return append_event_with_projection_and_outbox(
        session,
        aggregate_type="signal",
        aggregate_id="S-1",
        aggregate_version=version,
        event_type="SignalStateChanged",
        event_payload=event_payload if event_payload is not None else {"state": "ACTIVE"},
        idempotency_key=f"signal-event-{version}",
        projection_state=projection_state if projection_state is not None else {"state": "ACTIVE"},
        expected_projection_version=version - 1,
        outbox_destination="read-model-cache",
        outbox_payload=outbox_payload if outbox_payload is not None else {"refresh": "S-1"},
    )


def test_event_projection_and_outbox_are_written_together(session):
    event, projection, outbox = write(session)
    session.commit()

    assert event.aggregate_version == 1
    assert projection.last_event_id == event.event_id
    assert outbox.event_id == event.event_id
    assert session.execute(select(DomainEventRow)).scalars().all() == [event]
    assert session.execute(select(AggregateProjectionRow)).scalars().all() == [projection]
    assert session.execute(select(DomainOutboxRow)).scalars().all() == [outbox]


def test_transaction_rollback_removes_all_three_records(session):
    write(session)
    session.rollback()

    assert session.execute(select(DomainEventRow)).scalars().all() == []
    assert session.execute(select(AggregateProjectionRow)).scalars().all() == []
    assert session.execute(select(DomainOutboxRow)).scalars().all() == []


def test_exact_retry_is_idempotent_across_all_three_records(session):
    first = write(session)
    session.commit()
    retry = write(session)
    assert retry[0].event_id == first[0].event_id
    assert retry[1].last_event_id == first[1].last_event_id
    assert retry[2].outbox_id == first[2].outbox_id
    session.commit()

    assert len(session.execute(select(DomainEventRow)).scalars().all()) == 1
    assert len(session.execute(select(AggregateProjectionRow)).scalars().all()) == 1
    assert len(session.execute(select(DomainOutboxRow)).scalars().all()) == 1


def test_projection_conflict_does_not_commit_prior_event(session):
    write(session)
    session.commit()

    with pytest.raises(ProjectionConflict):
        append_event_with_projection_and_outbox(
            session,
            aggregate_type="signal",
            aggregate_id="S-1",
            aggregate_version=2,
            event_type="SignalStateChanged",
            event_payload={"state": "CLOSED"},
            idempotency_key="signal-event-2",
            projection_state={"state": "CLOSED"},
            expected_projection_version=0,
            outbox_destination="read-model-cache",
            outbox_payload={"refresh": "S-1"},
        )
    session.rollback()
    assert len(session.execute(select(DomainEventRow)).scalars().all()) == 1
    assert len(session.execute(select(AggregateProjectionRow)).scalars().all()) == 1
    assert len(session.execute(select(DomainOutboxRow)).scalars().all()) == 1


def test_outbox_same_event_destination_with_changed_payload_conflicts(session):
    first = write(session)
    session.commit()
    from app.database.domain_outbox import enqueue_domain_event

    with pytest.raises(DomainOutboxConflict):
        enqueue_domain_event(
            session,
            event_id=first[0].event_id,
            destination="read-model-cache",
            payload={"refresh": "different"},
        )
