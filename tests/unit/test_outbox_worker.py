from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.connection import Base
from app.database.event_store import append_event
from app.database.domain_outbox import enqueue_domain_event
from app.database.models import DomainOutboxRow
from app.database.outbox_worker import (
    OutboxLeaseError,
    claim_domain_outbox,
    mark_domain_outbox_delivered,
    retry_domain_outbox,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as value:
        yield value
    engine.dispose()


def add_outbox(session, key="e1", available_at=None):
    event = append_event(
        session,
        aggregate_type="test",
        aggregate_id=key,
        aggregate_version=1,
        event_type="Created",
        payload={},
        idempotency_key=key,
    )
    row = enqueue_domain_event(
        session,
        event_id=event.event_id,
        destination="test-sink",
        payload={"event": key},
    )
    if available_at is not None:
        row.available_at = available_at
    session.commit()
    return row


def test_claims_due_rows_and_increments_attempt(session):
    now = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)
    row = add_outbox(session, available_at=now - timedelta(seconds=1))
    claimed = claim_domain_outbox(session, owner="worker-a", now=now)
    session.commit()

    assert [item.outbox_id for item in claimed] == [row.outbox_id]
    assert row.status == "PROCESSING"
    assert row.attempts == 1
    assert row.lease_owner == "worker-a"
    assert row.lease_until == now + timedelta(seconds=30)


def test_future_rows_are_not_claimed(session):
    now = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)
    add_outbox(session, available_at=now + timedelta(minutes=1))
    assert claim_domain_outbox(session, owner="worker-a", now=now) == []


def test_expired_lease_can_be_reclaimed_by_another_worker(session):
    now = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)
    row = add_outbox(session, available_at=now - timedelta(seconds=1))
    first = claim_domain_outbox(session, owner="worker-a", now=now, lease_seconds=5)[0]
    session.commit()
    assert first.outbox_id == row.outbox_id

    reclaimed = claim_domain_outbox(
        session,
        owner="worker-b",
        now=now + timedelta(seconds=6),
        lease_seconds=5,
    )[0]
    session.commit()
    assert reclaimed.lease_owner == "worker-b"
    assert reclaimed.attempts == 2


def test_only_current_lease_owner_can_complete(session):
    now = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)
    row = add_outbox(session, available_at=now - timedelta(seconds=1))
    claim_domain_outbox(session, owner="worker-a", now=now)
    session.commit()

    with pytest.raises(OutboxLeaseError):
        mark_domain_outbox_delivered(session, outbox_id=row.outbox_id, owner="worker-b")
    delivered = mark_domain_outbox_delivered(
        session, outbox_id=row.outbox_id, owner="worker-a", now=now
    )
    session.commit()
    assert delivered.status == "DELIVERED"
    assert delivered.lease_owner is None


def test_retry_backoff_and_dead_letter_after_attempt_limit(session):
    now = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)
    row = add_outbox(session, available_at=now - timedelta(seconds=1))
    claim_domain_outbox(session, owner="worker-a", now=now, max_attempts=2)
    retry = retry_domain_outbox(
        session,
        outbox_id=row.outbox_id,
        owner="worker-a",
        error="temporary",
        max_attempts=2,
        retry_delay_seconds=10,
        now=now,
    )
    session.commit()
    assert retry.status == "PENDING"
    assert retry.available_at == now + timedelta(seconds=10)

    claimed = claim_domain_outbox(
        session,
        owner="worker-b",
        now=now + timedelta(seconds=11),
        max_attempts=2,
    )[0]
    session.commit()
    dead = retry_domain_outbox(
        session,
        outbox_id=row.outbox_id,
        owner="worker-b",
        error="final failure",
        max_attempts=2,
        now=now + timedelta(seconds=11),
    )
    session.commit()
    assert claimed.attempts == 2
    assert dead.status == "DEAD"
    assert dead.last_error == "final failure"


def test_expired_row_at_attempt_limit_is_dead_lettered(session):
    now = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)
    row = add_outbox(session, available_at=now - timedelta(seconds=1))
    claim_domain_outbox(session, owner="worker-a", now=now, lease_seconds=1, max_attempts=1)
    session.commit()

    claimed = claim_domain_outbox(
        session,
        owner="worker-b",
        now=now + timedelta(seconds=2),
        max_attempts=1,
    )
    session.commit()
    assert claimed == []
    assert row.status == "DEAD"
    assert row.lease_owner is None


def test_invalid_claim_limits_are_rejected(session):
    with pytest.raises(ValueError):
        claim_domain_outbox(session, owner="worker-a", limit=0)
    with pytest.raises(ValueError):
        claim_domain_outbox(session, owner="worker-a", max_attempts=0)
