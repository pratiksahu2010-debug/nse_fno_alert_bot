# Phase 14 — Shadow actor recovery and lifecycle

## Scope

This phase adds an opt-in recovery coordinator for the non-authoritative
per-symbol shadow observers. It reconstructs observation checkpoints from the
existing versioned event ledger using the verified snapshot/replay primitives
from earlier phases. Recovery remains isolated from `LiveRuntime`: it is not
started at application startup and does not alter the live signal pipeline.

## Recovery contract

- Aggregate type defaults to `shadow_actor`; the aggregate ID is the exact
  instrument key.
- Reducers and schema upcasters are injected by the caller and must be
  deterministic, side-effect-free functions.
- Each aggregate is replayed in its own SQLAlchemy session on a worker thread.
  The replay engine verifies snapshot anchors and SHA-256 checksums before
  using a snapshot.
- Work is bounded by a configurable concurrency limit and per-aggregate
  timeout. Any replay, schema, gap, checksum, timeout, or checkpoint-validation
  failure fails the entire recovery batch.
- No actor is changed until every checkpoint has replayed and validated.
  Registry restore validates the full batch before constructing any actor.
- Restored actors are seeded but do not start consuming until the registry's
  explicit `start()` call.
- Aggregates with no event history are skipped; the coordinator does not
  invent or infer state.

Checkpoint state is intentionally narrow: timezone-aware ISO-8601
`last_timestamp`, finite positive `last_price`, and non-negative integer
`processed`. It is diagnostic shadow-observation state only.

## Lifecycle

The coordinator exposes `STOPPED`, `STARTING`, `RECOVERING`, `READY`,
`FAILED`, and `STOPPING`. Failed recovery can be retried explicitly.
Shutdown waits for the active recovery critical section only up to its
configured caller timeout; it never waits indefinitely.

## Safety invariants

- No imports or calls to strategy modules, signal coordinator, trade/risk
  management, Telegram delivery, broker clients, or order APIs.
- No event append, snapshot write, projection write, outbox enqueue, or DB
  commit is performed by recovery.
- The recovery coordinator is not wired into `LiveRuntime` or FastAPI startup.
- Existing signal-generation, scoring, entry/exit, alert and order-disabled
  behavior is unchanged. `alert_only=true` and
  `order_placement_enabled=false` remain the production contract.
- No production migration, Render operation, environment change, restart, or
  deployment is part of this phase.

## Current integration boundary

The current live shadow actors do not yet emit domain checkpoint events.
Therefore, this phase supplies and tests the safe recovery mechanism, but it
will skip actors with no `shadow_actor` event history. A later, separately
reviewed phase may add shadow-only checkpoint event production; it must not
couple that work to signal generation or alert delivery.

## Tests

Unit tests cover successful event replay, empty history, fail-closed invalid
state, checksum mismatch, no partial actor restore, deferred actor start, and
bounded lifecycle shutdown. CI is the authoritative test result for this PR.
