"""Read-only projection parity audit against deterministic event replay.

This verifier diagnoses materialized-view drift. It never repairs projections,
writes events, publishes outbox records, or connects to the live signal runtime.
"""
from dataclasses import dataclass

from sqlalchemy import func, select

from .models import AggregateProjectionRow, DomainEventRow
from .replay import replay_aggregate


@dataclass(frozen=True)
class ProjectionAuditResult:
    ok: bool
    status: str
    aggregate_type: str
    aggregate_id: str
    projection_version: int
    latest_event_version: int
    replayed_event_count: int
    snapshot_version: int
    detail: str


def audit_projection(
    session,
    *,
    aggregate_type: str,
    aggregate_id: str,
    reducers: dict,
    upcasters: dict | None = None,
    target_schema_versions: dict | None = None,
    initial_state: dict | None = None,
) -> ProjectionAuditResult:
    """Compare one stored projection with a read-only replay at its version.

    Status values: EMPTY, PROJECTION_MISSING, PROJECTION_AHEAD,
    PROJECTION_STALE, ANCHOR_MISMATCH, STATE_MISMATCH, MATCH.
    Replay/schema/integrity errors are deliberately propagated to the caller
    rather than downgraded to a misleading successful audit.
    """
    if not isinstance(aggregate_type, str) or not aggregate_type.strip():
        raise ValueError("aggregate_type is required")
    if not isinstance(aggregate_id, str) or not aggregate_id.strip():
        raise ValueError("aggregate_id is required")

    latest = session.execute(
        select(func.max(DomainEventRow.aggregate_version)).where(
            DomainEventRow.aggregate_type == aggregate_type,
            DomainEventRow.aggregate_id == aggregate_id,
        )
    ).scalar_one()
    latest_version = int(latest or 0)
    projection = session.get(
        AggregateProjectionRow, (aggregate_type, aggregate_id)
    )

    if projection is None:
        status = "EMPTY" if latest_version == 0 else "PROJECTION_MISSING"
        return ProjectionAuditResult(
            ok=(status == "EMPTY"),
            status=status,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            projection_version=0,
            latest_event_version=latest_version,
            replayed_event_count=0,
            snapshot_version=0,
            detail=(
                "No events or projection exist for this aggregate."
                if status == "EMPTY"
                else "Event history exists but the materialized projection is missing."
            ),
        )

    projection_version = projection.aggregate_version
    if projection_version > latest_version:
        return ProjectionAuditResult(
            ok=False,
            status="PROJECTION_AHEAD",
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            projection_version=projection_version,
            latest_event_version=latest_version,
            replayed_event_count=0,
            snapshot_version=0,
            detail="Projection version is newer than the aggregate event ledger.",
        )

    anchor = session.execute(
        select(DomainEventRow).where(
            DomainEventRow.aggregate_type == aggregate_type,
            DomainEventRow.aggregate_id == aggregate_id,
            DomainEventRow.aggregate_version == projection_version,
        )
    ).scalar_one_or_none()
    if anchor is None or anchor.event_id != projection.last_event_id:
        return ProjectionAuditResult(
            ok=False,
            status="ANCHOR_MISMATCH",
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            projection_version=projection_version,
            latest_event_version=latest_version,
            replayed_event_count=0,
            snapshot_version=0,
            detail="Projection last_event_id does not identify its aggregate/version event.",
        )

    replay = replay_aggregate(
        session,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        reducers=reducers,
        upcasters=upcasters,
        target_schema_versions=target_schema_versions,
        target_version=projection_version,
        initial_state=initial_state,
    )

    if projection.state != replay.state:
        status = "STATE_MISMATCH"
        detail = "Projection state differs from deterministic event replay."
    elif projection_version < latest_version:
        status = "PROJECTION_STALE"
        detail = "Projection matches its event prefix but is behind the latest event."
    else:
        status = "MATCH"
        detail = "Projection state, event anchor and aggregate version match replay."

    return ProjectionAuditResult(
        ok=(status == "MATCH"),
        status=status,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        projection_version=projection_version,
        latest_event_version=latest_version,
        replayed_event_count=replay.replayed_event_count,
        snapshot_version=replay.snapshot_version,
        detail=detail,
    )
