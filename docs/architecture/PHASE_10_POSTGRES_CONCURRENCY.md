# Phase 10 — PostgreSQL migration and concurrency verification

## Purpose

Add a real PostgreSQL service to GitHub Actions and exercise the database
contracts that SQLite cannot validate.

## CI coverage

The CI workflow starts an ephemeral PostgreSQL 16 service, applies migrations
0001 through 0005 using the actual migration runner, then verifies the ledger.
Integration tests use independent SQLAlchemy sessions and threads to check:

- Unique aggregate-version constraint under concurrent writers: exactly one
  writer may create the aggregate/version event.
- Concurrent retry using the same idempotency key resolves to one event ID.
- SELECT FOR UPDATE SKIP LOCKED prevents a second worker from claiming a row
  while the first worker holds the transaction lock.

The database is ephemeral to the CI job. No user or production database is
referenced.

## Limitations

These are focused concurrency checks, not a full soak or crash-recovery drill.
They do not prove Neon-specific networking, failover, connection pool behavior,
or Telegram delivery guarantees. A disposable Neon staging rehearsal remains
required before any production migration or rollout.

No strategy, signal, risk, alert, Telegram or order-safety behavior is changed.
