# Phase 12 — Snapshot integrity checks

## Scope and safety

This phase adds SHA-256 integrity verification to immutable aggregate snapshots.
It does not connect replay to LiveRuntime, actors, strategies, trade management,
Telegram, broker APIs or order placement. Existing signal and alert behavior is
unchanged. No production migration is run by this change.

## Contract

- Snapshot state is serialized as canonical JSON (sorted keys, compact
  separators, UTF-8, finite JSON values only) before hashing with SHA-256.
- A checksum row is written in the same caller-owned transaction as the
  snapshot row.
- Replay validates the snapshot's aggregate/event anchor and checksum before
  using its state.
- Missing checksums and checksum mismatches fail closed with an explicit
  integrity error; replay never falls back to potentially corrupted state.
- The checksum table is additive. Existing snapshots receive an empty
  sentinel and must be re-created from trusted event history before replay.

## Verification

Unit tests cover deterministic hashing, exact retry, rollback, state tampering
and replay rejection. PostgreSQL CI applies migration 0006 and checks the
updated migration ledger. Production migration and recovery rehearsal remain
blocked pending explicit approval and a disposable staging database test.
