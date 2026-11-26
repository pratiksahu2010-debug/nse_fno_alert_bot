# Phase 9 — Domain outbox lease and retry state machine

## Purpose and safety boundary

This phase adds bounded lease/retry state transitions for domain_outbox. It
does not add a dispatcher or invoke any publisher, Telegram sender, broker or
order API. The existing Telegram alert_outbox is unchanged.

## State transitions

- PENDING -> PROCESSING when due and claimed.
- PROCESSING -> PROCESSING when an expired lease is reclaimed by another
  worker.
- PROCESSING -> DELIVERED when the current lease owner records success.
- PROCESSING -> PENDING with a future available_at when a retry is scheduled
  and attempts remain.
- PROCESSING -> DEAD after the configured maximum attempt count.
- An expired PROCESSING row already at the attempt limit is moved to DEAD
  rather than leased again.

Claims use SELECT FOR UPDATE SKIP LOCKED on PostgreSQL, increment attempts and
assign an owner/expiry. The caller must commit the lease before doing external
work. Completion/retry requires the current owner token. The helper functions
do not commit and do not perform delivery.

## Tests and remaining gates

SQLite tests cover due filtering, attempt counting, lease expiry/reclaim,
owner checks, delivery completion, retry delay and dead-letter transitions.
SQLite does not prove PostgreSQL concurrent SKIP LOCKED behavior. Add a
multi-connection PostgreSQL test and a crash/reclaim drill before enabling a
real dispatcher.

No strategy, signal, risk, alert or order-safety behavior is changed.
