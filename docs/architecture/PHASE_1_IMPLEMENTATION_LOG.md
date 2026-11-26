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

### Verification status

- Source and test changes pushed to the draft PR branch.
- **Tests not executed in this environment.** Direct Git clone was unavailable because the execution environment could not resolve `github.com`. The added test must run in GitHub Actions or a local checkout before merge.
- No strategy module, strategy setting, indicator, signal condition, risk rule, alert formatter, environment variable, production database or Render service was changed.
- This is an isolated infrastructure change, not completion of the actor/CQRS/event-sourcing modernization and not production approval.
