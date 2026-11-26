"""Immutable aggregate snapshot persistence with integrity digests.

Snapshots are anchored to an existing domain event and remain inert until a
replay coordinator explicitly consumes them. This module has no runtime hooks.
"""
import hashlib
import json

from sqlalchemy import ForeignKey, String, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from .connection import Base
from .models import AggregateSnapshotRow, DomainEventRow


class SnapshotChecksumRow(Base):
    """One immutable SHA-256 digest for each persisted snapshot."""
    __tablename__ = "aggregate_snapshot_checksums"
    snapshot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("aggregate_snapshots.snapshot_id", ondelete="CASCADE"),
        primary_key=True,
    )
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)


class SnapshotConflict(RuntimeError):
    """A different snapshot already occupies the aggregate version."""


class SnapshotAnchorError(ValueError):
    """The snapshot does not point to the matching aggregate event."""


class SnapshotIntegrityError(RuntimeError):
    """The persisted snapshot state does not match its stored checksum."""


def snapshot_checksum(state: dict) -> str:
    """Return a stable digest for JSON-compatible state.

    Sorting keys and compact separators make the digest independent of dict
    insertion order. Non-JSON values and NaN/Infinity are rejected.
    """
    if not isinstance(state, dict):
        raise TypeError("snapshot state must be a dictionary")
    try:
        encoded = json.dumps(
            state, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("snapshot state must contain finite JSON-compatible values") from exc
    return hashlib.sha256(encoded).hexdigest()


def verify_snapshot_checksum(session, snapshot) -> str:
    """Verify and return a snapshot's digest; missing digests fail closed."""
    row = session.get(SnapshotChecksumRow, snapshot.snapshot_id)
    if row is None:
        raise SnapshotIntegrityError(
            f"snapshot {snapshot.snapshot_id} has no integrity checksum"
        )
    actual = snapshot_checksum(snapshot.state)
    if row.checksum != actual:
        raise SnapshotIntegrityError(
            f"snapshot {snapshot.snapshot_id} checksum mismatch"
        )
    return actual


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
    """Store one immutable snapshot and checksum without committing the caller's transaction."""
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
    digest = snapshot_checksum(state)

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
            session.add(SnapshotChecksumRow(snapshot_id=row.snapshot_id, checksum=digest))
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
            stored = session.get(SnapshotChecksumRow, existing.snapshot_id)
            if stored is not None and stored.checksum == digest:
                return existing
        raise SnapshotConflict(
            f"snapshot already exists for {aggregate_type}/{aggregate_id} version {aggregate_version}"
        ) from exc


def load_latest_snapshot(
    session, *, aggregate_type: str, aggregate_id: str, max_version: int | None = None
):
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
