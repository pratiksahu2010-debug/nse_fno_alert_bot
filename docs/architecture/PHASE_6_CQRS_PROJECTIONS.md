# Phase 6 — CQRS aggregate read projections

## Purpose and boundary

This phase adds a generic materialized read-model table and an optimistic,
transaction-owned projection writer. It is not connected to the live signal
pipeline or event ingestion. Existing signal queries and alert behavior remain
unchanged.

## Contract

Each aggregate has at most one current projection, keyed by aggregate type and
ID. The projection records its aggregate version, JSON state, last event ID
and update time. The event anchor must exist and match the aggregate/version.

Updates require the caller's expected current version and use a conditional
SQL UPDATE as a compare-and-swap guard. A stale writer cannot silently replace
a newer projection. Exact retries at the current version are idempotent;
different content at the same version raises ProjectionConflict. Insert races
are surfaced as ProjectionConflict. The helper never commits the caller's
transaction.

## Migration and verification

0004_aggregate_projections.sql is additive and depends on the domain_events
table. SQLite tests cover insert/update, stale writer rejection, exact retry,
same-version content conflicts, anchor validation and caller rollback.
PostgreSQL concurrency/isolation tests are still required.

## Explicitly not implemented

- Live event-to-projection subscription
- Atomic event + projection + outbox transaction
- Concrete trading signal/trade read models
- Projection rebuild orchestration
- Runtime query migration or cutover
- PostgreSQL contention tests and failure injection

No strategy, signal, risk, alert or order-safety behavior is modified.
