# Phase 1 — Architecture Audit (initial source review)

**Audit baseline:** `main` at `930e360c785a70ab31f614972a74cc285dcd772c` (2026-11-23)
**Scope:** infrastructure, persistence, reliability, performance, recovery, observability and deployment only.
**Protected scope:** `app/strategies/**`, strategy configuration, indicators, signal conditions, risk/entry/exit behavior and alert formatting are frozen. No files have been changed in those areas.

## Audit completeness and evidence

This is an initial source-based audit, not a completed production certification. The GitHub integration exposed selected files and repository metadata, but not a complete checkout or a runnable environment. The README reports 19 passing unit tests on the delivered build; this audit has **not independently executed** those tests. No CI status was reported for the baseline commit. A full tree inventory, complete history/PR review, local regression run, real PostgreSQL integration tests and load/failure tests remain required.

## Current module map

- `app/main.py`: FastAPI app, import-time settings/engine/schema creation, background runtime initialization, health/status/ping/root endpoints.
- `app/runtime.py`: live orchestration, Upstox client and WebSocket, candle builders, mutable per-instrument state, strategy invocation, trade-state persistence and delivery worker startup.
- `app/config.py`: Pydantic settings and environment compatibility.
- `app/market_data/**`: Upstox REST, V3 WebSocket, protobuf decode, universe, tick/candle models and candle building.
- `app/strategies/**`: exactly two frozen existing strategies (ORB_GAP and MOMENTUM_EXPLOSION); no changes permitted.
- `app/signals/**`: signal data model and in-memory coordinator.
- `app/risk/**`: existing structural stop, target and trade-state logic; preserve behavior.
- `app/database/**`: SQLAlchemy ORM, synchronous engine/session, repository and SQL schema.
- `app/alerts/**`: formatter, Telegram client, persistent outbox and delivery worker.
- `scripts/**`: bootstrap/backtest utilities (complete inventory pending).
- `tests/**`: README reports 19 tests; test file inventory and execution pending.
- `config/**`: reviewed universe and eligible-symbol inputs; must not be silently altered.

## Data flow and ownership (observed)

Upstox V3 WebSocket -> `WebsocketManager` -> `LiveRuntime.on_tick` -> shared 1m/5m `CandleBuilder` instances -> completed 5m candle processing -> frozen strategies -> `SignalCoordinator` -> synchronous SQLAlchemy transaction persisting signal, signal event, risk levels, trade state and alert outbox -> `DeliveryWorker` -> Telegram.

Trade lifecycle updates are performed in the same runtime callback using synchronous database access. Startup performs universe refresh and historical warmup before starting the WebSocket and Telegram worker tasks.

## Findings

### P0 — Critical
- None confirmed from the inspected source. Absence of a confirmed P0 is not a production-readiness assertion.

### P1 — High
1. **No per-entity actor ownership:** runtime state is held in shared dictionaries/sets and two shared candle builders; there is no mailbox, sequential actor command boundary or explicit cross-symbol isolation.
2. **Not event-sourced:** `signal_events` records signal lifecycle labels but lacks aggregate sequence/version, event schema version, idempotency/correlation/causation fields and complete state-transition history. `active_trades.state_json` is overwritten.
3. **Startup and readiness contract:** initialization runs in a background task; `/health` combines liveness/readiness and returns HTTP 200 with `ok:false` while dependencies/runtime are not ready. No distinct `/ready` route was observed.
4. **Schema lifecycle:** `Base.metadata.create_all(engine)` runs at import time. A SQL schema file exists, but a versioned migration/rollback runner was not observed in inspected startup code.
5. **Outbox delivery is at-least-once:** lease ownership and bounded attempts exist, but an external Telegram acceptance followed by a crash before DB completion can duplicate a message. Exactly-once delivery cannot be guaranteed without destination idempotency support.
6. **No proven full restart/replay recovery:** today's signal dedupe and momentum cooldown are restored, but candle-builder state, open ranges and all runtime state are not generally snapshotted/restored.

### P2 — Medium
1. **Blocking database operations in async paths:** synchronous SQLAlchemy sessions and queries are called from async tick/candle callbacks and the async delivery worker.
2. **Shared sequential processing bottleneck:** one callback path processes closed candles serially; slow work for one symbol can delay other symbols.
3. **Unbounded candle retention:** `CandleBuilder.closed` is not pruned in the inspected implementation. The `seen` set has a coarse cap; current/history buffers have other limits.
4. **Persistence/coordinator ordering:** `SignalCoordinator.accept` mutates in-memory dedupe state before `SignalRepository.save_with_alert` commits. A persistence failure can leave in-memory state ahead of durable state.
5. **Limited observability:** current health covers DB/runtime/feed/stale instruments but not actor/mailbox metrics, worker task health, outbox backlog/age, DB pool metrics, replay/snapshot status or resource utilization.
6. **Universe/startup diagnostics:** warmup catches per-instrument errors and continues; readiness criteria should explicitly quantify required coverage rather than rely on log interpretation.

### P3 — Improvements
- Structured JSON logging with correlation IDs and redaction tests.
- Explicit worker/task supervision and named lifecycle states.
- Bounded queue and worker metrics, latency histograms and resource profiling.
- Retention/archival policy for health and delivery history after policy review.
- Documented operational runbooks and rollback drills.

## Existing safeguards to preserve

- Upstox REST request serialization, request pacing and bounded retry budget.
- WebSocket reconnect with exponential backoff and jitter, batched subscriptions and stale-key tracking.
- Historical warmup semaphore bounded to six.
- Rolling per-symbol candle history capped at 1,200 in runtime.
- Persistent alert outbox with DB lease, bounded attempts and delivery history.
- Existing signal and trade tables and current Telegram payload behavior.
- Alert-only guarantee: no order placement, modification or cancellation.

## Dependency and migration risks

- SQLAlchemy is synchronous; changing to async DB access requires driver, pool, transaction and test changes. Do not mix sync/async session lifecycles.
- PostgreSQL is production target; SQLite is useful for fast unit tests but cannot validate `FOR UPDATE SKIP LOCKED`, locking, isolation or concurrency semantics.
- Existing production tables and Neon data must remain intact. Additive expand/contract migrations only; no destructive migration until parity and backup/restore are proven.
- Telegram cannot provide a general exactly-once guarantee for a send accepted immediately before a client crash.
- Render free-tier memory/CPU and single-instance behavior constrain actor counts, queue sizes and background worker design.
- Universe and strategy config are out of scope for architecture changes.

## Required implementation sequence

1. Obtain a complete checkout and inventory all files, dependencies, tests, workflows, migrations, Render config, history and PRs.
2. Run the unchanged baseline suite and compilation; preserve exact outputs.
3. Add architecture docs, state ownership boundaries and operational baselines.
4. Fix bounded resource/lifecycle defects with tests (first candidate: candle closed-bar retention); verify strategy/config files remain byte-for-byte unchanged.
5. Introduce a bounded actor runtime in shadow mode; existing runtime remains authoritative.
6. Add additive event ledger, optimistic sequence append, snapshots and replay with side effects disabled during replay.
7. Add read-only projections and improve transactional outbox retry/dead-letter observability without changing Telegram payload/alert types.
8. Run PostgreSQL concurrency, recovery, failure-injection, API compatibility and resource tests.
9. Demonstrate shadow parity and reversible migration before proposing any production cutover.

## Initial quality gates

| Gate | Result | Evidence |
|---|---|---|
| Repository metadata/main baseline | PASS | Main head recorded |
| Key source inspection | PARTIAL | Selected modules inspected |
| Complete repository inventory | BLOCKED | Full tree not exposed |
| Baseline full test run | BLOCKED | No runnable checkout |
| Actor isolation/backpressure | FAIL | Not present |
| Event ledger/sequence guarantees | FAIL | Not present |
| Snapshot/replay | FAIL | Not present |
| Outbox durability | PARTIAL | Durable leases/retries; external delivery remains at-least-once |
| Versioned migrations/rollback | BLOCKED | Runner not verified |
| PostgreSQL concurrency tests | NOT TESTED | No test DB access |
| Failure injection/performance profile | NOT TESTED | No runnable environment |
| Strategy preservation | PASS (inspection only) | No strategy files edited |
| Shadow parity | NOT TESTED | No actor implementation |
| Production readiness | NOT TESTED | Gates remain open |

## Change log

- Initial audit document only. No application code, strategy modules, configuration, environment variables, database records or Render services changed.
