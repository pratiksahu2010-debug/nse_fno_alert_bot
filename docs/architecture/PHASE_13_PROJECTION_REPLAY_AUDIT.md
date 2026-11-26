# Phase 13 — Read-only projection replay audit

## Scope

Adds a read-only diagnostic that compares a CQRS projection with deterministic
replay of its authoritative aggregate event history. It is an offline audit
primitive, not an automatic repair mechanism and not connected to LiveRuntime.

## Outcomes

- `EMPTY`: no event history and no projection exist.
- `PROJECTION_MISSING`: events exist but the projection is absent.
- `PROJECTION_AHEAD`: projection version exceeds the latest event version.
- `ANCHOR_MISMATCH`: projection last_event_id does not identify the event at
  its declared aggregate version.
- `STATE_MISMATCH`: replayed state differs from projection state.
- `PROJECTION_STALE`: projection matches its event prefix but trails the
  latest committed event.
- `MATCH`: state, event anchor and aggregate version all agree.

Replay errors, sequence gaps, unsupported event schemas, missing upcasters and
snapshot integrity errors propagate to the caller. They are not hidden as a
successful or generic mismatch result.

## Safety invariants

- Performs database reads only; no commit, projection update, event append,
  outbox enqueue, alert send, broker request or order placement.
- Does not import or call the signal runtime, strategies or actor registry.
- No migration is required and no existing signal/alert behavior changes.
- A future repair operation must be a separate, explicitly approved workflow.

## Tests

Unit tests cover all statuses, exact parity, stale projection, corrupted state,
bad event anchor, projection ahead of ledger and no-mutation behavior.
