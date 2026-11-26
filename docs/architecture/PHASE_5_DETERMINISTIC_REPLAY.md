# Phase 5 — Deterministic side-effect-free replay

## Purpose and safety boundary

This phase adds a generic aggregate replay engine that can rebuild a state
dictionary from an immutable snapshot and a contiguous event suffix. It is
read-only and deliberately disconnected from LiveRuntime, actors, strategies,
trade management, Telegram and all broker/order interfaces.

Reducers and schema upcasters are injected pure functions. The replay module
does not import or invoke any live application service. No live state is
restored or changed.

## Replay contract

- Select the newest snapshot for the aggregate, optionally bounded by a target
  aggregate version.
- Verify the snapshot's last-event anchor still identifies the same aggregate
  and version.
- Read the subsequent events in aggregate-version order.
- Require a contiguous sequence; report a gap rather than silently skipping
  events.
- Resolve an event reducer by event type.
- Apply explicitly registered schema upcasters one version at a time.
- Reject unknown event types, missing upcasters, newer-than-target schemas and
  reducers/upcasters that return non-dictionary state.
- Return reconstructed state, aggregate version, replayed event count and
  starting snapshot version.

The replay engine does not write snapshots, events, projections or outbox
records. It does not publish messages or perform external side effects.
Reducers and upcasters must be deterministic and side-effect-free by contract.

## Tests

SQLite tests cover genesis replay, snapshot plus suffix replay, sequence gaps,
target versions beyond available history, unknown event types, schema
upcasting, missing/newer schema handling and input immutability. PostgreSQL
isolation/concurrency and operational recovery drills remain separate gates.

## Explicitly not implemented

- Production event producers or live signal-path integration
- Concrete strategy/trade lifecycle reducers
- Automatic snapshot scheduling, retention or compaction
- Runtime actor restoration
- CQRS projections or transactional outbox
- PostgreSQL concurrency and recovery drills

No strategy, signal, risk, alert or order-safety behavior is changed.
