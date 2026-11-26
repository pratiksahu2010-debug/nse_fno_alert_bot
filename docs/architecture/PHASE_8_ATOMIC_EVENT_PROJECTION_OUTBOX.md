# Phase 8 — Atomic event, projection and outbox writes

## Purpose and boundary

This phase adds a transaction coordinator that composes the Phase 3 event
append, Phase 6 CQRS projection update and a new durable domain outbox record.
All three are written through one caller-owned SQLAlchemy session transaction.

The new domain_outbox is distinct from the existing Telegram alert_outbox.
It records durable delivery intent only. No dispatcher, external publisher,
Telegram sender or broker/order integration is added.

## Transaction contract

append_event_with_projection_and_outbox performs:
1. Append or resolve the idempotent domain event.
2. Insert/update the projection using expected-version compare-and-swap.
3. Enqueue one outbox row per event and destination.

It never commits. The caller commits once after success or rolls back on
failure. A failure in projection or outbox work must be followed by rollback;
the test suite verifies that a projection conflict does not leave a partial
event after rollback. Event idempotency and the unique event/destination key
make retries safe when the full logical input is unchanged.

## Outbox model

The durable row contains event ID, destination, JSON payload, status, attempts,
availability time, lease fields, error and timestamps. This phase does not
claim exactly-once delivery. Dispatch, leases, retries, poison-message policy,
dead-letter handling and external side-effect idempotency are later work.

## Migration and tests

Migration 0005 is additive and leaves the existing Telegram outbox untouched.
SQLite tests cover atomic creation, rollback, full-operation idempotent retry,
projection-conflict rollback and outbox payload conflicts. PostgreSQL
concurrency and crash-recovery tests remain required.

No strategy, signal, risk, alert formatting or order-safety behavior is changed.
