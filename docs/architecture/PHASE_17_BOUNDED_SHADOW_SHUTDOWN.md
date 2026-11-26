# Phase 17 — Bounded shadow actor shutdown

## Finding

The Phase 16 session exposed a timeout for checkpoint flush, but the actor
registry shutdown path awaited each actor mailbox drain without a timeout.
A slow or stuck consumer could therefore keep `ShadowActorSession.stop()`
waiting indefinitely before it reached the checkpoint flush timeout.

## Change

- `SymbolActor.stop(timeout=...)` bounds mailbox drain and consumer completion.
- A timeout returns `False`, leaves the actor non-accepting, and does not
  cancel a worker that may still be finishing accepted work.
- A later stop call can retry and complete the drain.
- `ShadowActorRegistry.stop(timeout=...)` returns false if any actor cannot
  drain within the bound.
- `ShadowActorSession.stop()` now checks the registry result and remains in
  `STOPPING` without submitting final checkpoints or stopping the producer
  until all accepted actor observations have drained.

## Safety boundary

This change is limited to lifecycle management for diagnostic shadow actors.
It does not change strategy evaluation, indicators, signal scoring,
entry/exit conditions, trade/risk state, Telegram alerts, broker access,
order placement, or the authoritative live runtime. Alert-only mode and
disabled order placement remain unchanged. No LiveRuntime/FastAPI integration,
production migration, database operation, Render action, environment change,
restart, or deployment is performed.

## Validation

Adds timeout-and-retry tests at actor and registry levels, plus a session test
that verifies a timed-out actor drain leaves the session in `STOPPING` and
keeps the checkpoint producer alive for a safe retry. PostgreSQL-backed CI and
the compile step are required before this phase is considered validated.
