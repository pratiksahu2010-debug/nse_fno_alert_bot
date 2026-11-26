# Phase 2 — Shadow virtual actor runtime

**Branch:** `architecture/phase-2-shadow-actors`
**Base:** `main`
**Implementation commits:**
- `6d7df6a8fb62352f482e3421366a5442731db04e` — bounded actor runtime
- `c9d92168b5c39f904fbb98d1a9b1f96f6e3c15d4` — non-blocking tick fan-out from LiveRuntime
- `9afbca7545012a659b727f241ca155246316a9e4` — actor tests
- `3b670ef894d61c6a8beb11c632bac1075c08c266` — compact shutdown summary

## Purpose

Introduce a bounded per-instrument actor/mailbox layer in shadow mode. The existing `LiveRuntime` remains the sole authority for candle construction, strategy evaluation, trade lifecycle, persistence and Telegram alerts.

## Design

- Actors are created lazily per instrument key.
- Each actor owns one bounded `asyncio.Queue` and one serial consumer task.
- Default mailbox capacity is 256 ticks per instrument.
- Registry actor count is bounded by the validated universe size (minimum 1).
- Tick fan-out uses `put_nowait`; a full shadow mailbox drops that observation and increments a counter. It never waits on or back-pressures the authoritative signal pipeline.
- Each actor records only observation telemetry: processed count, dropped count, last timestamp and current queue depth.
- Shutdown stops acceptance, drains queued observations and closes actor tasks.
- The registry logs aggregate counters only; it does not log every tick or all per-symbol snapshots.

## Safety boundary

The shadow actors do **not**:
- Invoke ORB_GAP or MOMENTUM_EXPLOSION.
- Calculate indicators, score setups or create signals.
- Write to the database or mutate trade state.
- Format or send Telegram alerts.
- Place orders.

No strategy files, strategy settings, indicators, signal conditions, risk rules or alert formats are changed by this phase. The existing sequential runtime remains authoritative.

## Tests added

`tests/unit/test_shadow_actors.py` covers:
- Bounded mailbox behavior and non-blocking drop policy.
- Per-symbol isolation and maximum actor count.
- Rejection of new ticks after registry shutdown.

## Verification and rollout

- Tests have been added but **not executed in this environment**.
- No successful CI result has been observed for this branch head.
- Run `pytest -q` and `python -m compileall -q app scripts tests` before merge.
- Compare actor processed/drop counts against feed ingress during a market-hours shadow run; verify bounded queue depth and no impact to legacy alert latency.
- This phase does not switch any production signal authority to actors and does not complete CQRS, event sourcing, snapshots, replay or durable recovery.
- No Render deploy/restart, environment-variable change, database migration or production data mutation was performed.
