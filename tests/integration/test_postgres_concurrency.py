"""Real PostgreSQL migration and concurrency tests for CI."""
from concurrent.futures import ThreadPoolExecutor
from os import getenv
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.domain_outbox import enqueue_domain_event
from app.database.event_store import AggregateVersionConflict, append_event
from app.database.migrator import apply_migrations, verify_migrations
from app.database.outbox_worker import claim_domain_outbox
from app.database.snapshots import save_snapshot, verify_snapshot_checksum


DATABASE_URL = getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is not configured")


@pytest.fixture(scope="session")
def postgres_engine():
    engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=5, pool_pre_ping=True)
    apply_migrations(engine)
    yield engine
    engine.dispose()


def test_postgres_migrations_apply_and_verify(postgres_engine):
    result = verify_migrations(postgres_engine)
    assert result == {"ok": True, "current_version": 6}


def test_postgres_snapshot_checksum_round_trip(postgres_engine):
    aggregate_id = str(uuid4())
    with Session(postgres_engine) as session:
        event = append_event(
            session,
            aggregate_type="snapshot-test",
            aggregate_id=aggregate_id,
            aggregate_version=1,
            event_type="Created",
            payload={"state": "ready"},
            idempotency_key=f"snapshot-{aggregate_id}",
        )
        snapshot = save_snapshot(
            session,
            aggregate_type="snapshot-test",
            aggregate_id=aggregate_id,
            aggregate_version=1,
            state={"state": "ready"},
            last_event_id=event.event_id,
        )
        session.commit()
        assert len(verify_snapshot_checksum(session, snapshot)) == 64


def test_postgres_aggregate_version_unique_constraint_serializes_writers(postgres_engine):
    aggregate_id = str(uuid4())
    barrier = Barrier(2)

    def append_with_key(key):
        with Session(postgres_engine) as session:
            barrier.wait(timeout=10)
            try:
                event = append_event(
                    session,
                    aggregate_type="concurrency-test",
                    aggregate_id=aggregate_id,
                    aggregate_version=1,
                    event_type="Created",
                    payload={"value": 1},
                    idempotency_key=key,
                )
                session.commit()
                return ("created", event.event_id)
            except AggregateVersionConflict:
                session.rollback()
                return ("conflict", None)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(append_with_key, ("writer-a", "writer-b")))

    assert sorted(result[0] for result in results) == ["conflict", "created"]


def test_postgres_same_idempotency_key_is_safe_under_concurrent_retry(postgres_engine):
    aggregate_id = str(uuid4())
    barrier = Barrier(2)

    def append_retry():
        with Session(postgres_engine) as session:
            barrier.wait(timeout=10)
            event = append_event(
                session,
                aggregate_type="idempotency-test",
                aggregate_id=aggregate_id,
                aggregate_version=1,
                event_type="Created",
                payload={"value": "same"},
                idempotency_key=f"retry-{aggregate_id}",
            )
            session.commit()
            return event.event_id

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: append_retry(), range(2)))

    assert ids[0] == ids[1]


def test_postgres_skip_locked_prevents_double_claim(postgres_engine):
    aggregate_id = str(uuid4())
    with Session(postgres_engine) as setup:
        event = append_event(
            setup,
            aggregate_type="outbox-test",
            aggregate_id=aggregate_id,
            aggregate_version=1,
            event_type="Created",
            payload={},
            idempotency_key=f"outbox-event-{aggregate_id}",
        )
        enqueue_domain_event(
            setup,
            event_id=event.event_id,
            destination="concurrency-test",
            payload={"id": aggregate_id},
        )
        setup.commit()

    first = Session(postgres_engine)
    second = Session(postgres_engine)
    try:
        claimed_first = claim_domain_outbox(first, owner="worker-one", limit=1)
        claimed_second = claim_domain_outbox(second, owner="worker-two", limit=1)
        assert len(claimed_first) == 1
        assert claimed_second == []
        first.commit()
        second.rollback()
    finally:
        first.close()
        second.close()
