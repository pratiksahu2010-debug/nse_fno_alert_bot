"""Lease and retry state transitions for the durable domain outbox.

This module does not publish messages or invoke external side effects.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select

from .models import DomainOutboxRow


class OutboxLeaseError(RuntimeError):
    """An outbox lease is absent, expired/reclaimed or owned by another worker."""


def claim_domain_outbox(
    session,
    *,
    owner: str,
    limit: int = 50,
    lease_seconds: int = 30,
    max_attempts: int = 8,
    now: datetime | None = None,
) -> list[DomainOutboxRow]:
    """Claim due rows using SELECT FOR UPDATE SKIP LOCKED where supported.

    Attempts increment when a row is claimed. Expired rows at their maximum
    attempt count are moved to DEAD instead of being leased again. The caller
    owns the transaction and must commit the lease before doing any delivery.
    """
    if not isinstance(owner, str) or not owner.strip():
        raise ValueError("owner is required")
    if type(limit) is not int or limit < 1:
        raise ValueError("limit must be a positive integer")
    if type(lease_seconds) is not int or lease_seconds < 1:
        raise ValueError("lease_seconds must be a positive integer")
    if type(max_attempts) is not int or max_attempts < 1:
        raise ValueError("max_attempts must be a positive integer")
    now = now or datetime.now(timezone.utc)
    if not isinstance(now, datetime):
        raise TypeError("now must be a datetime")

    due = or_(
        and_(
            DomainOutboxRow.status == "PENDING",
            DomainOutboxRow.available_at <= now,
        ),
        and_(
            DomainOutboxRow.status == "PROCESSING",
            DomainOutboxRow.lease_until.is_not(None),
            DomainOutboxRow.lease_until <= now,
        ),
    )

    exhausted = session.execute(
        select(DomainOutboxRow)
        .where(due, DomainOutboxRow.attempts >= max_attempts)
        .with_for_update(skip_locked=True)
    ).scalars().all()
    for row in exhausted:
        row.status = "DEAD"
        row.lease_owner = None
        row.lease_until = None
        if not row.last_error:
            row.last_error = "maximum delivery attempts exhausted"
        row.updated_at = now

    candidates = session.execute(
        select(DomainOutboxRow)
        .where(due, DomainOutboxRow.attempts < max_attempts)
        .order_by(DomainOutboxRow.available_at, DomainOutboxRow.created_at)
        .with_for_update(skip_locked=True)
        .limit(limit)
    ).scalars().all()

    lease_until = now + timedelta(seconds=lease_seconds)
    for row in candidates:
        row.status = "PROCESSING"
        row.attempts += 1
        row.lease_owner = owner
        row.lease_until = lease_until
        row.updated_at = now
    session.flush()
    return candidates


def mark_domain_outbox_delivered(
    session, *, outbox_id: str, owner: str, now: datetime | None = None
) -> DomainOutboxRow:
    """Mark a claimed row delivered when the caller still owns its lease."""
    row = _owned_processing_row(session, outbox_id, owner)
    row.status = "DELIVERED"
    row.lease_owner = None
    row.lease_until = None
    row.last_error = None
    row.updated_at = now or datetime.now(timezone.utc)
    session.flush()
    return row


def retry_domain_outbox(
    session,
    *,
    outbox_id: str,
    owner: str,
    error: str,
    max_attempts: int = 8,
    retry_delay_seconds: int = 15,
    now: datetime | None = None,
) -> DomainOutboxRow:
    """Schedule a bounded retry or move the row to DEAD after the final attempt."""
    if type(max_attempts) is not int or max_attempts < 1:
        raise ValueError("max_attempts must be a positive integer")
    if type(retry_delay_seconds) is not int or retry_delay_seconds < 0:
        raise ValueError("retry_delay_seconds must be a non-negative integer")
    if not isinstance(error, str) or not error.strip():
        raise ValueError("error is required")

    row = _owned_processing_row(session, outbox_id, owner)
    now = now or datetime.now(timezone.utc)
    row.last_error = error[:2000]
    row.lease_owner = None
    row.lease_until = None
    row.updated_at = now
    if row.attempts >= max_attempts:
        row.status = "DEAD"
    else:
        row.status = "PENDING"
        row.available_at = now + timedelta(seconds=retry_delay_seconds)
    session.flush()
    return row


def _owned_processing_row(session, outbox_id: str, owner: str) -> DomainOutboxRow:
    if not isinstance(outbox_id, str) or not outbox_id.strip():
        raise ValueError("outbox_id is required")
    if not isinstance(owner, str) or not owner.strip():
        raise ValueError("owner is required")
    row = session.get(DomainOutboxRow, outbox_id)
    if row is None or row.status != "PROCESSING" or row.lease_owner != owner:
        raise OutboxLeaseError("outbox row is not leased by this worker")
    return row
