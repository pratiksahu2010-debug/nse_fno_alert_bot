# Phase 3 — Additive domain event ledger

## Scope and safety boundary

This phase introduces the persistence primitive for a versioned append-only
domain event ledger. It is infrastructure-only and deliberately inert:
LiveRuntime, SignalCoordinator, both strategy modules, risk calculations,
trade management, Telegram formatting/delivery and order-safety controls are
not wired to or changed by this phase.

The existing signal_events table remains the legacy signal lifecycle log.
domain_events is a new table; this phase does not backfill, rewrite or delete
legacy rows and does not claim the application is fully event-sourced.

## Schema contract

Each row records an event ID, aggregate type, aggregate ID, caller-supplied
positive aggregate version, event type, schema version, JSON payload, unique
idempotency key, optional correlation and causation IDs, source, occurrence
time and database recording time.

Uniqueness constraints enforce one event per aggregate version and one row per
idempotency key. Aggregate versions are supplied by the caller; the helper
intentionally does not calculate MAX(version) + 1, which is unsafe under
concurrent writers. A sequence conflict must be reconciled by the owning
aggregate/transaction coordinator.

## Transaction and retry behavior

append_event uses a SQLAlchemy savepoint to isolate uniqueness conflicts and
does not commit the caller's transaction. On SQLite it explicitly starts the
outer transaction before opening a savepoint, avoiding sqlite3 legacy-mode
savepoint release behavior that can otherwise commit independently. A retry
with the same idempotency key
and identical logical content returns the existing event. Reusing the key for
different content raises IdempotencyConflict; a different key colliding with
an occupied aggregate version raises AggregateVersionConflict.

The caller remains responsible for committing or rolling back. This is
necessary for a future atomic event + projection + outbox transaction, but
that integration is intentionally deferred until aggregate ownership and
transaction boundaries are proven.

## Migration

app/database/migrations/0002_domain_events.sql is additive PostgreSQL DDL.
No migration was applied to any database. The current app still uses
Base.metadata.create_all() at startup; do not deploy this branch until the
schema-creation/migration lifecycle is reconciled and an approved migration
procedure is chosen. No production database, Render service, secret or
environment variable was touched.

## Tests added

SQLite unit coverage includes event append, exact idempotent retry, key reuse
with changed payload, aggregate-version collision, aggregate isolation,
transaction rollback and invalid input. SQLite does not validate PostgreSQL
locking, transaction isolation or concurrent writers. Tests have not yet been
executed in this environment; run the full suite and PostgreSQL integration
tests before merge.

## Explicitly pending

- PostgreSQL concurrent append tests and conflict/retry policy
- Aggregate version ownership/locking strategy
- Event schema evolution and upcasters
- Snapshot model, checkpointing and deterministic replay
- Replay mode with all external side effects disabled
- CQRS read projections and transactional outbox integration
- Failure injection, shadow parity and recovery drills
- Replace import-time create_all() with versioned migrations only after a
  separately reviewed migration/rollback plan

No strategy or signal-generation logic is modified.
