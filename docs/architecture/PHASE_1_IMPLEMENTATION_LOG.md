# Phase 1 implementation log

## Change 001 — Bound closed-candle retention

**Branch:** `architecture/phase-1-audit`
**Baseline:** `930e360c785a70ab31f614972a74cc285dcd772c`
**Implementation commit:** `53449e9f2a524ef4a0b099b7fa1498b71fc80f5c`
**Regression-test commit:** `2b9e60141b4d37c193becaabac1c7a83dfe89671`

### Problem

The shared 1-minute and 5-minute `CandleBuilder` instances retained every closed candle in `self.closed` for the lifetime of the process. The map had no retention limit, so memory use grew throughout long-running service operation.

### Change

- Replace the unbounded closed-candle dictionary with an insertion-ordered cache.
- Add a configurable positive `max_closed_candles` limit (default 10,000).
- Maintain a per-instrument closed-bar watermark. Once a bar is closed, delayed ticks for that bar or any older bar are rejected even after the candle is evicted from the cache.
- Preserve sorting of ticks inside an open bar, OHLCV aggregation, bar boundary alignment and existing method signatures for current callers.

### Regression coverage

Extended `tests/unit/test_candle_builder.py` to verify:
- Existing 5-minute boundary and OHLCV behavior.
- Closed-candle cache stays within its configured bound.
- A delayed tick cannot recreate a bar that has already been closed and evicted.

## Change 002 — Separate liveness from readiness

**Implementation commit:** `d814788b8af52bfdc9cc31703ee9a84b7a2e037c`
**Regression-test commit:** `bab1a26d9bcecdc4b630fcd9c87f7754d2fc9873`

### Problem

The legacy `/health` endpoint reports readiness fields but always responds with HTTP 200, including while initialization is incomplete or the feed is disconnected. A platform health check cannot distinguish a live HTTP process from a ready signal runtime using HTTP status alone.

### Change

- Add `GET /live` as a lightweight process-liveness response.
- Add `GET /ready` with dependency checks for database connectivity, completed initialization, running runtime, non-empty validated universe and connected market feed.
- `/ready` returns HTTP 200 only when every readiness check passes; otherwise it returns HTTP 503 with explicit failed check names.
- Preserve the existing `/health`, `/status`, `/ping`, and root response contracts.
- Keep Render's configured health check on `/health` for now; changing platform health-check behavior requires separate verification and approval.

### Regression coverage

Added `tests/unit/test_readiness.py` for ready state, disconnected feed, initialization/startup failure, database failure and empty universe. These are pure helper tests and do not require production credentials or database access.

## Verification status

- Source and tests are committed to the draft PR branch.
- **Tests have not been executed in this environment.** Direct Git clone was unavailable because the execution environment could not resolve `github.com`; no passing CI result has been observed for these commits.
- Run `pytest -q` and `python -m compileall -q app scripts tests` before merge.
- PostgreSQL concurrency, replay, failure-injection, resource profiling and shadow-parity gates remain open.
- No strategy module, strategy setting, indicator, signal condition, risk rule, alert formatter, environment variable, production database or Render service was changed.
- These are incremental infrastructure changes, not completion of actor/CQRS/event-sourcing modernization and not production approval.
