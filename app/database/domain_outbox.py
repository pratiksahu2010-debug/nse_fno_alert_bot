"""Durable, transaction-owned outbox primitives for domain events.

This is separate from the existing Telegram alert_outbox and has no dispatcher.
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .models import DomainEventRow, DomainOutboxRow


class DomainOutboxConflict(RuntimeError):
    """An event/destination pair already has different outbox content."""


class DomainOutboxAnchorError(ValueError):
    """The outbox row references an unknown domain event."""


def enqueue_domain_event(session, *, event_id: str, destination: str, payload: dict):
    """Enqueue a domain event delivery record without committing the transaction."""
    if not isinstance(event_id, str) or not event_id.strip():
        raise ValueError("event_id is required")
    if not isinstance(destination, str) or not destination.strip():
        raise ValueError("destination is required")
    if not isinstance(payload, dict):
        raise TypeError("outbox payload must be a dictionary")

    event = session.execute(
        select(DomainEventRow).where(DomainEventRow.event_id == event_id)
    ).scalar_one_or_none()
    if event is None:
        raise DomainOutboxAnchorError("event_id does not exist in the domain event ledger")

    row = DomainOutboxRow(
        event_id=event_id,
        destination=destination,
        payload=payload,
        available_at=datetime.now(timezone.utc),
    )
    try:
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
            select(DomainOutboxRow).where(
                DomainOutboxRow.event_id == event_id,
                DomainOutboxRow.destination == destination,
            )
        ).scalar_one_or_none()
        if existing is not None and existing.payload == payload:
            return existing
        raise DomainOutboxConflict(
            f"outbox content conflicts for event {event_id} destination {destination}"
        ) from exc
