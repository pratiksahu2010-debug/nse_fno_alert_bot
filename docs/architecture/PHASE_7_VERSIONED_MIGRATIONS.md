# Phase 7 — Versioned database migrations

## Purpose

Replace implicit ORM table creation with an explicit, checksummed migration
lifecycle. Application startup becomes read-only with respect to schema state:
it verifies that every migration is applied and refuses runtime initialization
when the database is behind or a migration file has changed.

## Migration command

Run the explicit administrative command with the intended DATABASE_URL:

    python -m scripts.migrate

The runner supports PostgreSQL only, acquires a transaction-scoped advisory
lock, creates a schema_migrations ledger, applies ordered SQL files in one
transaction, and records each filename and SHA-256 checksum. A failure rolls
back the whole migration transaction. Already-applied files must match their
recorded checksum; unknown database versions fail closed.

The current numbered migrations are 0001 through 0004. Migration 0001 is
idempotent DDL and supports adoption of an existing database whose tables were
previously created by SQLAlchemy create_all(): the existing tables are left in
place and the initial migration records the baseline before applying later
additive changes.

## Startup behavior

main.py no longer calls Base.metadata.create_all() at import time. Before
market-data warmup or runtime initialization, it calls verify_migrations()
as a read-only gate. If the schema ledger is missing, incomplete or changed,
the runtime remains stopped and startup_error records the reason. The health
and readiness endpoints can still start so the operator can diagnose it.

This means a future deployment must first run the migration command against
the intended database. No migration is automatically applied by app startup.

## Safety and verification

Unit tests cover migration discovery, sequential numbering, checksum
calculation, SQL statement splitting, missing ledger, exact ledger verification,
checksum drift, unknown versions and refusal to run migrations on SQLite.
The PostgreSQL advisory lock and DDL transaction require a staging Neon/
PostgreSQL test before production use.

No database has been migrated by this change. No production Render service,
environment variable, secret or database was accessed or changed.

## Rollback policy

Migrations are forward-only in this runner. Rollback requires a separately
reviewed compensating migration and backup/restore plan; the runner never
automatically drops tables or reverses DDL. Do not edit an applied migration:
add a new version instead.

No strategy, signal, risk, alert, or order-safety behavior is changed.
