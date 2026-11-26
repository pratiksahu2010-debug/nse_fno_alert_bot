# Phase 16 — Opt-in shadow session orchestration

## Scope

Introduce an explicit lifecycle object that coordinates the Phase 14 recovery
coordinator, Phase 15 checkpoint producer, and shadow actor registry. It is
not imported by `LiveRuntime`, FastAPI startup, or the authoritative market
data path. A caller must construct and start it explicitly.

## Startup contract

1. Start the checkpoint producer before any actor can emit a checkpoint.
2. Replay verified `shadow_actor` events for the configured instrument keys.
3. Validate the complete recovery batch and restore actors atomically.
4. Start actor consumers only after recovery succeeds.
5. Accept observations only while the session is READY.

A replay or validation failure leaves the registry stopped and the session
FAILED. The producer is asked to stop before the exception is propagated.

## Shutdown contract

1. Registry stops accepting new observations and drains accepted actor mailboxes.
2. Persist a final snapshot for each actor with an observation.
3. Flush the checkpoint queue.
4. Stop the producer only after a successful flush.
5. Stop the recovery coordinator and mark the session STOPPED.

A flush/stop timeout returns false and leaves the session in STOPPING so the
caller can retry; it is never reported as a successful shutdown.

## Boundaries

- This object is opt-in and is not wired into application startup or
  `LiveRuntime`.
- It writes only versioned `shadow_actor/ObservationCheckpointed` events.
- It does not read or modify signal, strategy, trade, risk, Telegram, broker,
  order, or alert state.
- It does not change existing signal calculations, signal conditions, alert
  behavior, or the alert-only / order-placement-disabled safeguards.
- It makes no production migration, database, Render, environment, restart,
  or deployment changes.
- The existing production runtime remains authoritative and unchanged.

## Validation

Unit tests cover recovery-before-actor-start ordering, rejection of ticks before
explicit start, final checkpoint persistence during shutdown, and fail-closed
startup when replay validation fails. PostgreSQL CI remains the authoritative
integration signal; SQLite unit tests do not substitute for production
database rehearsal.

## Operational gate

This phase provides orchestration primitives only. It is not approval to
enable the shadow session in staging or production. A separate reviewed
staging rehearsal must verify database connectivity, migration state,
single-writer ownership, bounded shutdown under database failure, and
observability before any runtime integration is proposed.
