"""Optimistic, transaction-owned CQRS aggregate projection primitives.

This module is not wired to event ingestion or the live signal runtime.
"""
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from .models import AggregateProjectionRow, DomainEventRow


class ProjectionConflict(RuntimeError):
    """A projection update lost its expected-version compare-and-swap."""


class ProjectionAnchorError(ValueError):
    """A projection does not point to the matching domain event."""


def save_projection(
    session,
    *,
    aggregate_type: str,
    aggregate_id: str,
    aggregate_version: int,
    state: dict,
    last_event_id: str,
    expected_current_version: int = 0,
):
    """Insert/update a projection using optimistic aggregate-version control.

    The event anchor must exist and match the aggregate/version. Updates use a
    conditional SQL UPDATE so concurrent writers cannot silently overwrite a
    newer projection. This function never commits the caller's transaction.
    """
    for name, value in (
        ("aggregate_type", aggregate_type),
        ("aggregate_id", aggregate_id),
        ("last_event_id", last_event_id),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} is required")
    if type(aggregate_version) is not int or aggregate_version < 1:
        raise ValueError("aggregate_version must be a positive integer")
    if type(expected_current_version) is not int or expected_current_version < 0:
        raise ValueError("expected_current_version must be a non-negative integer")
    if not isinstance(state, dict):
        raise TypeError("projection state must be a dictionary")
    if aggregate_version <= expected_current_version:
        raise ValueError("aggregate_version must advance beyond expected_current_version")

    event = session.execute(
        select(DomainEventRow).where(DomainEventRow.event_id == last_event_id)
    ).scalar_one_or_none()
    if event is None or (
        event.aggregate_type != aggregate_type
        or event.aggregate_id != aggregate_id
        or event.aggregate_version != aggregate_version
    ):
        raise ProjectionAnchorError("projection anchor does not match its aggregate/version")

    connection = session.connection()
    if connection.dialect.name == "sqlite":
        driver_connection = connection.connection.driver_connection
        if not driver_connection.in_transaction:
            connection.exec_driver_sql("BEGIN")

    current = session.get(AggregateProjectionRow, (aggregate_type, aggregate_id))
    if current is None:
        if expected_current_version != 0:
            raise ProjectionConflict("projection does not exist at the expected version")
        row = AggregateProjectionRow(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            aggregate_version=aggregate_version,
            state=state,
            last_event_id=last_event_id,
        )
        try:
            with session.begin_nested():
                session.add(row)
                session.flush()
            return row
        except IntegrityError as exc:
            raise ProjectionConflict("projection was concurrently created") from exc

    if current.aggregate_version == aggregate_version:
        if current.last_event_id == last_event_id and current.state == state:
            return current
        raise ProjectionConflict("different projection content already exists at this version")
    if current.aggregate_version != expected_current_version:
        raise ProjectionConflict(
            f"expected projection version {expected_current_version}, found {current.aggregate_version}"
        )

    result = session.execute(
        update(AggregateProjectionRow)
        .where(
            AggregateProjectionRow.aggregate_type == aggregate_type,
            AggregateProjectionRow.aggregate_id == aggregate_id,
            AggregateProjectionRow.aggregate_version == expected_current_version,
        )
        .values(
            aggregate_version=aggregate_version,
            state=state,
            last_event_id=last_event_id,
        )
    )
    if result.rowcount != 1:
        raise ProjectionConflict("projection compare-and-swap lost to another writer")
    return session.get(AggregateProjectionRow, (aggregate_type, aggregate_id))


def load_projection(session, *, aggregate_type: str, aggregate_id: str):
    """Read the current materialized view for one aggregate."""
    if not isinstance(aggregate_type, str) or not aggregate_type.strip():
        raise ValueError("aggregate_type is required")
    if not isinstance(aggregate_id, str) or not aggregate_id.strip():
        raise ValueError("aggregate_id is required")
    return session.get(AggregateProjectionRow, (aggregate_type, aggregate_id))
