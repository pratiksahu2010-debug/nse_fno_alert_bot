"""Immutable aggregate snapshot persistence primitives.

Snapshots are anchored to an existing domain event and remain inert until a
replay coordinator explicitly consumes them. This module has no runtime hooks.
"""
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .models import AggregateSnapshotRow, DomainEventRow


class SnapshotConflict(RuntimeError):
    """A different snapshot already occupies the aggregate version."""


class SnapshotAnchorError(ValueError):
    """The snapshot does not point to the matching aggregate event."""


def save_snapshot(
    session,
    *,
    aggregate_type: str,
    aggregate_id: str,
    aggregate_version: int,
    state: dict,
    last_event_id: str,
    schema_version: int = 1,
):
    """Store one immutable snapshot without committing the caller's transaction."""
    for name, value in (
        ("aggregate_type", aggregate_type),
        ("aggregate_id", aggregate_id),
        ("last_event_id", last_event_id),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} is required")
    if type(aggregate_version) is not int or aggregate_version < 1:
        raise ValueError("aggregate_version must be a positive integer")
    if type(schema_version) is not int or schema_version < 1:
        raise ValueError("schema_version must be a positive integer")
    if not isinstance(state, dict):
        raise TypeError("snapshot state must be a dictionary")

    event = session.execute(
        select(DomainEventRow).where(DomainEventRow.event_id == last_event_id)
    ).scalar_one_or_none()
    if event is None:
        raise SnapshotAnchorError("last_event_id does not exist in the domain event ledger")
    if (
        event.aggregate_type != aggregate_type
        or event.aggregate_id != aggregate_id
        or event.aggregate_version != aggregate_version
    ):
        raise SnapshotAnchorError("snapshot aggregate/version does not match its anchor event")

    row = AggregateSnapshotRow(
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        aggregate_version=aggregate_version,
        schema_version=schema_version,
        state=state,
        last_event_id=last_event_id,
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
            select(AggregateSnapshotRow).where(
                AggregateSnapshotRow.aggregate_type == aggregate_type,
                AggregateSnapshotRow.aggregate_id == aggregate_id,
                AggregateSnapshotRow.aggregate_version == aggregate_version,
            )
        ).scalar_one_or_none()
        if existing is not None and (
            existing.schema_version == schema_version
            and existing.state == state
            and existing.last_event_id == last_event_id
        ):
            return existing
        raise SnapshotConflict(
            f"snapshot already exists for {aggregate_type}/{aggregate_id} version {aggregate_version}"
        ) from exc


def load_latest_snapshot(session, *, aggregate_type: str, aggregate_id: str, max_version: int | None = None):
    """Return the newest snapshot at or before max_version, or None."""
    if not isinstance(aggregate_type, str) or not aggregate_type.strip():
        raise ValueError("aggregate_type is required")
    if not isinstance(aggregate_id, str) or not aggregate_id.strip():
        raise ValueError("aggregate_id is required")
    if max_version is not None and (type(max_version) is not int or max_version < 1):
        raise ValueError("max_version must be a positive integer when supplied")

    query = select(AggregateSnapshotRow).where(
        AggregateSnapshotRow.aggregate_type == aggregate_type,
        AggregateSnapshotRow.aggregate_id == aggregate_id,
    )
    if max_version is not None:
        query = query.where(AggregateSnapshotRow.aggregate_version <= max_version)
    return session.execute(
        query.order_by(AggregateSnapshotRow.aggregate_version.desc()).limit(1)
    ).scalar_one_or_none()
