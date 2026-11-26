# Phase 4 — Immutable aggregate snapshots

## Purpose and boundary

This phase adds an inert persistence primitive for aggregate snapshots. It does
not invoke snapshots from LiveRuntime, replay signals, restore live strategy
state, or change any signal/alert behavior.

## Contract

A snapshot contains aggregate type and ID, the exact aggregate version,
snapshot schema version, JSON state, the ID of the domain event it represents,
and a creation timestamp. A foreign key anchors each snapshot to a real
domain_events row. The repository verifies that event aggregate identity and
version match the snapshot before writing.

Only one snapshot may occupy an aggregate version. An exact retry returns the
existing snapshot; different state at the same aggregate version raises
SnapshotConflict. Snapshot writes do not commit the caller's transaction.
SQLite savepoint handling explicitly begins the outer transaction to preserve
rollback behavior under sqlite3 legacy transaction mode.

load_latest_snapshot can return the newest snapshot or the newest snapshot
at or before a requested aggregate version. It does not replay events after
the snapshot; replay is a later, separately gated phase.

## Migration and safety

0003_aggregate_snapshots.sql is additive and depends on the Phase 3
domain_events table. No database was modified and no migration was applied.
The current application still calls Base.metadata.create_all() at startup.
Do not deploy until a versioned migration runner, rollback plan and
create_all() removal strategy are reviewed.

## Tests

SQLite tests cover anchoring, mismatched aggregate/version rejection, exact
retry, conflicting snapshot content, bounded latest-snapshot lookup and
caller-owned rollback. PostgreSQL concurrency and migration tests are not
included yet. CI must pass before merge.

## Explicitly not implemented

- Event replay after the snapshot
- Snapshot scheduling/compaction or retention
- Snapshot schema upcasters
- State restoration into runtime actors
- Replay side-effect isolation
- PostgreSQL locking/concurrency tests
- CQRS projections and transactional outbox integration

No strategy modules, signal conditions, risk behavior, alert formatting or
order-safety settings are modified.
