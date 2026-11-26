# Phase 15 — Shadow checkpoint event production

## Scope

Add an opt-in producer that converts the existing non-authoritative shadow
actor's observation snapshots into versioned `shadow_actor` domain events.
The producer is an injectable checkpoint sink; this phase does not enable it
in `LiveRuntime` or application startup.

## Event contract

- Aggregate type: `shadow_actor`.
- Aggregate ID: exact instrument key.
- Event type: `ObservationCheckpointed`, schema version 1.
- Payload: timezone-aware ISO-8601 `last_timestamp`, finite positive
  `last_price`, and non-negative integer `processed`.
- Aggregate versions are loaded from the event ledger and incremented
  sequentially by one producer instance.
- Idempotency keys are deterministic per aggregate/version.
- The existing append-only event store and unique aggregate-version constraint
  enforce idempotency and reject competing writers.

## Bounded asynchronous behavior

- Actor callbacks are rate-limited before snapshot serialization (30 seconds by
  default) and call only the producer's non-blocking `submit()`; no database
  operation occurs on the actor consumer.
- A bounded queue holds at most one pending key per instrument. Repeated
  updates for a queued instrument coalesce to the latest checkpoint.
- Per-instrument minimum interval throttles event volume.
- Database work runs in worker threads with one SQLAlchemy session per
  operation and bounded retry attempts.
- Queue-full, invalid payload, throttle, persistence and failure counters are
  exposed by the producer's diagnostic snapshot.
- `flush()` and `stop()` have caller-supplied timeouts. A timeout is reported
  as incomplete draining; it is not represented as a successful flush.

## Recovery compatibility

The event name and payload shape match the Phase 14 recovery reducer contract.
The replay engine reconstructs the latest checkpoint from sequential events;
its aggregate version is authoritative. Recovery still verifies snapshot
checksums and event anchors before using any snapshot.

## Safety invariants

- The producer writes only diagnostic shadow-observation events.
- No signal, strategy, trade, risk, Telegram, broker, order or alert data is
  imported or modified.
- The producer is not instantiated by `LiveRuntime` and is not connected to
  FastAPI startup. The optional actor sink is only used when explicitly
  injected by a caller.
- The existing live signal pipeline and signal/alert behavior remain
  authoritative and unchanged; order placement remains disabled.
- No production migration, Render operation, environment change, restart,
  deployment, or production database operation is part of this phase.

## Operational boundary

Exactly one producer instance should own an aggregate at a time. Multiple
writers are rejected by the unique aggregate-version constraint rather than
silently overwriting each other. A later integration phase must define
single-writer ownership, startup recovery ordering, graceful shutdown order,
and a production/staging persistence rehearsal before enabling this sink in
the live runtime.

## Tests

Tests cover coalescing, sequential aggregate versions, throttling, invalid
payload rejection, actor-to-sink callback behavior, database persistence and
graceful drain. GitHub Actions is the authoritative validation result.
