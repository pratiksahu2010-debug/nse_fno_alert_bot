"""Deterministic, side-effect-free aggregate replay primitives.

Reducers and upcasters are injected as pure functions. This module has no
imports from the live runtime, strategies, broker, Telegram or order layers.
"""
from copy import deepcopy
from dataclasses import dataclass
from typing import Callable

from sqlalchemy import select

from .models import AggregateSnapshotRow, DomainEventRow


class ReplayError(RuntimeError):
    """Base class for deterministic replay failures."""


class ReplayGapError(ReplayError):
    """An aggregate event sequence is incomplete."""


class UnknownEventTypeError(ReplayError):
    """No reducer was registered for an encountered event type."""


class MissingUpcasterError(ReplayError):
    """An event schema needs an upcaster that was not registered."""


class EventSchemaVersionError(ReplayError):
    """An event schema is newer than the configured replay schema."""


@dataclass(frozen=True)
class ReplayResult:
    state: dict
    aggregate_version: int
    replayed_event_count: int
    snapshot_version: int


def replay_aggregate(
    session,
    *,
    aggregate_type: str,
    aggregate_id: str,
    reducers: dict[str, Callable[[dict, dict], dict]],
    upcasters: dict[tuple[str, int], Callable[[dict], dict]] | None = None,
    target_schema_versions: dict[str, int] | None = None,
    target_version: int | None = None,
    initial_state: dict | None = None,
) -> ReplayResult:
    """Rebuild one aggregate using a snapshot and a contiguous event suffix.

    The reducer signature is reducer(state_copy, payload_copy) -> new_state.
    Reducers and upcasters must be deterministic and side-effect-free. The
    replay engine itself performs reads only and never commits or publishes.
    """
    if not isinstance(aggregate_type, str) or not aggregate_type.strip():
        raise ValueError("aggregate_type is required")
    if not isinstance(aggregate_id, str) or not aggregate_id.strip():
        raise ValueError("aggregate_id is required")
    if target_version is not None and (
        type(target_version) is not int or target_version < 1
    ):
        raise ValueError("target_version must be a positive integer")
    if initial_state is not None and not isinstance(initial_state, dict):
        raise TypeError("initial_state must be a dictionary")
    if not isinstance(reducers, dict):
        raise TypeError("reducers must be a dictionary")

    upcasters = upcasters or {}
    target_schema_versions = target_schema_versions or {}

    snapshot_query = select(AggregateSnapshotRow).where(
        AggregateSnapshotRow.aggregate_type == aggregate_type,
        AggregateSnapshotRow.aggregate_id == aggregate_id,
    )
    if target_version is not None:
        snapshot_query = snapshot_query.where(
            AggregateSnapshotRow.aggregate_version <= target_version
        )
    snapshot = session.execute(
        snapshot_query.order_by(AggregateSnapshotRow.aggregate_version.desc()).limit(1)
    ).scalar_one_or_none()

    if snapshot is None:
        state = deepcopy(initial_state or {})
        start_version = 0
        snapshot_version = 0
    else:
        anchor = session.execute(
            select(DomainEventRow).where(
                DomainEventRow.event_id == snapshot.last_event_id
            )
        ).scalar_one_or_none()
        if anchor is None or (
            anchor.aggregate_type != aggregate_type
            or anchor.aggregate_id != aggregate_id
            or anchor.aggregate_version != snapshot.aggregate_version
        ):
            raise ReplayGapError("snapshot anchor does not match its aggregate/version")
        state = deepcopy(snapshot.state)
        start_version = snapshot.aggregate_version
        snapshot_version = snapshot.aggregate_version

    event_query = select(DomainEventRow).where(
        DomainEventRow.aggregate_type == aggregate_type,
        DomainEventRow.aggregate_id == aggregate_id,
        DomainEventRow.aggregate_version > start_version,
    )
    if target_version is not None:
        event_query = event_query.where(
            DomainEventRow.aggregate_version <= target_version
        )
    events = session.execute(
        event_query.order_by(DomainEventRow.aggregate_version.asc())
    ).scalars().all()

    expected_version = start_version + 1
    replayed = 0
    for event in events:
        if event.aggregate_version != expected_version:
            raise ReplayGapError(
                f"expected aggregate version {expected_version}, got {event.aggregate_version}"
            )
        reducer = reducers.get(event.event_type)
        if reducer is None:
            raise UnknownEventTypeError(
                f"no reducer registered for event type {event.event_type!r}"
            )

        payload = deepcopy(event.payload)
        current_schema = event.schema_version
        target_schema = target_schema_versions.get(event.event_type, current_schema)
        if type(target_schema) is not int or target_schema < 1:
            raise ValueError("target schema versions must be positive integers")
        if current_schema > target_schema:
            raise EventSchemaVersionError(
                f"event {event.event_type!r} schema {current_schema} exceeds target {target_schema}"
            )
        while current_schema < target_schema:
            upcaster = upcasters.get((event.event_type, current_schema))
            if upcaster is None:
                raise MissingUpcasterError(
                    f"missing upcaster for {event.event_type!r} schema {current_schema}"
                )
            payload = upcaster(deepcopy(payload))
            if not isinstance(payload, dict):
                raise TypeError("event upcasters must return dictionaries")
            current_schema += 1

        state = reducer(deepcopy(state), payload)
        if not isinstance(state, dict):
            raise TypeError("event reducers must return dictionaries")
        expected_version += 1
        replayed += 1

    actual_version = expected_version - 1
    if target_version is not None and actual_version != target_version:
        raise ReplayGapError(
            f"requested version {target_version}, reconstructed only through {actual_version}"
        )

    return ReplayResult(
        state=state,
        aggregate_version=actual_version,
        replayed_event_count=replayed,
        snapshot_version=snapshot_version,
    )
