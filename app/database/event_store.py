"""Append-only domain event persistence primitives.

This module is intentionally not wired into LiveRuntime or signal generation.
Callers must append within their own SQLAlchemy transaction and supply the
aggregate version they have already serialized/validated.
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .models import DomainEventRow


class EventStoreError(RuntimeError):
    """Base class for event-store contract violations."""


class IdempotencyConflict(EventStoreError):
    """An idempotency key was reused for a different logical event."""


class AggregateVersionConflict(EventStoreError):
    """An aggregate version is already occupied by another event."""


def append_event(
    session,
    *,
    aggregate_type: str,
    aggregate_id: str,
    aggregate_version: int,
    event_type: str,
    payload: dict,
    idempotency_key: str,
    schema_version: int = 1,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    source: str = "application",
    occurred_at=None,
):
    """Append one event without committing the caller's transaction.

    Aggregate version and idempotency key are explicit inputs: this helper
    never guesses a sequence using MAX(version)+1, which races under concurrent
    writers. A unique constraint is the final concurrency guard. An exact
    retry with the same key returns the original row.
    """
    required = {
        "aggregate_type": aggregate_type,
        "aggregate_id": aggregate_id,
        "event_type": event_type,
        "idempotency_key": idempotency_key,
    }
    if any(not isinstance(value, str) or not value.strip() for value in required.values()):
        raise ValueError("aggregate type/id, event type and idempotency key are required")
    if type(aggregate_version) is not int or aggregate_version < 1:
        raise ValueError("aggregate_version must be a positive integer")
    if type(schema_version) is not int or schema_version < 1:
        raise ValueError("schema_version must be a positive integer")
    if not isinstance(payload, dict):
        raise TypeError("event payload must be a dictionary")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("source is required")
    for name, value in (("correlation_id", correlation_id), ("causation_id", causation_id)):
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError(f"{name} must be a non-empty string when supplied")
    if occurred_at is not None and not isinstance(occurred_at, datetime):
        raise TypeError("occurred_at must be a datetime when supplied")

    row = DomainEventRow(
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        aggregate_version=aggregate_version,
        event_type=event_type,
        schema_version=schema_version,
        payload=payload,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        causation_id=causation_id,
        source=source,
        occurred_at=occurred_at or datetime.now(timezone.utc),
    )
    try:
        # sqlite3's legacy transaction mode does not start a DB transaction for
        # SAVEPOINT alone. Releasing that first savepoint can therefore commit
        # it outside the caller's transaction. Explicitly begin the outer
        # SQLite transaction so caller rollback semantics match PostgreSQL.
        connection = session.connection()
        if connection.dialect.name == "sqlite":
            driver_connection = connection.connection.driver_connection
            if not driver_connection.in_transaction:
                connection.exec_driver_sql("BEGIN")
        with session.begin_nested():
            session.add(row)
            session.flush()
        return row
    except IntegrityError as exc:
        existing = session.execute(
            select(DomainEventRow).where(
                DomainEventRow.idempotency_key == idempotency_key
            )
        ).scalar_one_or_none()
        if existing is not None:
            same_event = (
                existing.aggregate_type == aggregate_type
                and existing.aggregate_id == aggregate_id
                and existing.aggregate_version == aggregate_version
                and existing.event_type == event_type
                and existing.schema_version == schema_version
                and existing.payload == payload
                and existing.correlation_id == correlation_id
                and existing.causation_id == causation_id
                and existing.source == source
            )
            if same_event:
                return existing
            raise IdempotencyConflict(
                f"idempotency key {idempotency_key!r} already identifies another event"
            ) from exc
        raise AggregateVersionConflict(
            f"{aggregate_type}/{aggregate_id} version {aggregate_version} is already used"
        ) from exc
