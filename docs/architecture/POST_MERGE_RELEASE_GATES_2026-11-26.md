# Post-merge release gates — 2026-11-26

## Repository status

- Architecture integration PR #22 is merged into `main`.
- Legacy-schema migration-adoption test PR #23 is merged into `main`.
- PR #23's GitHub Actions PostgreSQL 16 job passed: 112 tests in 1.84 seconds; Python compile check passed.
- Main-branch CI run #41 for commit `daf72688581fb3f56b8ab6b004d82fac09b51f7a` completed successfully. The PostgreSQL service, full pytest job and Python compile step all passed.
- There are no open pull requests at the time of this review.

This is an engineering status record, not production-release approval.

## Hard safety invariants

1. Keep the application signal-only. No broker order placement, modification, or cancellation.
2. Keep `alert_only=true` and `order_placement_enabled=false`.
3. Do not change the ORB + GAP or Momentum Explosion strategy definitions, indicator inputs, signal scoring, entry/exit behavior, risk calculations, or Telegram message contract as part of infrastructure hardening.
4. Keep shadow actor orchestration opt-in and separate from authoritative `LiveRuntime` startup until a separate staging parity review passes.
5. Never run schema migrations against production as part of this checklist.

## Remaining blockers (not safely automatable from repository access alone)

### A. Frozen F&O universe

The checked-in `config/fno_eligible_symbols.txt` and `config/nse_fno_universe.json` are intentionally empty. Before paper/staging alerts can be evaluated:

- Obtain the current official NSE F&O eligible underlying list for the intended trading date.
- Generate the Upstox instrument mapping with a valid Analytics Token.
- Cross-check each eligible underlying against the BOD master; verify exchange, instrument type, expiry, lot size, token and index keys.
- Reject duplicates, expired contracts, non-F&O cash symbols and unresolved tokens.
- Review and commit the frozen snapshot. Do not enable an auto-refresh that can silently change the trading universe.

### B. Mid-session data continuity

Automatic missing-candle backfill after a WebSocket reconnect is not implemented. A disconnected feed can leave stale instruments even after the socket reconnects.

Before live alert enablement, implement and test bounded, rate-limited historical gap repair:
- Track last contiguous completed candle timestamp per instrument.
- On reconnect, fetch the missing 1-minute/5-minute interval in API-compliant chunks.
- Validate timestamps, duplicates, OHLC invariants and session boundaries.
- Rebuild indicators only from ordered, completed candles.
- Keep the instrument unavailable until its gap is repaired; never manufacture candles or silently resume with a hole.
- Add tests for partial gaps, multi-window gaps, API throttling, overlapping responses, stale responses and repair failure.

### C. Live-feed protocol verification

The decoder currently has synthetic schema-fixture coverage, not a captured packet from this user's authorized Upstox account. Obtain a sanitized, non-secret sample from the actual V3 feed and verify LTPC, full-feed, market status, exchange timestamps, instrument keys, empty/partial packets and reconnect subscription restoration. Do not put access tokens or account identifiers into fixtures or logs.

### D. Database rehearsal

CI uses ephemeral PostgreSQL 16. Before any staging rollout:

1. Create an isolated staging database from a recent production backup or a representative sanitized copy.
2. Verify backup integrity and document restore steps before migration.
3. Inspect actual schema, migration ledger, extensions, indexes, row counts and existing signal rows.
4. Run the migration adoption path on staging only.
5. Verify checksums, row preservation, constraints, index validity, advisory-lock behavior and migration duration.
6. Rehearse restore from the pre-migration backup and record recovery time.
7. Never point a test or migration command at the production database.

### E. Render and paper-market soak

No Render service, secret, environment variable, deployment or restart has been changed by this work. A user-controlled staging service and credentials are required.

- Confirm build/start commands and Python version.
- Set secrets only in Render's secret environment; never commit them.
- Confirm `/live`, `/ready`, `/health` and `/status` semantics.
- Verify database, universe, runtime, feed and stale-instrument counts.
- Run a paper/replay soak over normal and failure scenarios: reconnect, stale feed, delayed/out-of-order ticks, queue saturation, DB outage, restart during checkpoint, outbox retry and graceful shutdown.
- Compare emitted signals with the pre-modernization baseline and require zero order requests.
- Record CPU, memory, database pool usage, queue high-water marks, feed staleness, recovery time and outbox age.

## Release decision

**Current decision: NOT PRODUCTION-READY / STAGING GATES OPEN.**

The merged code and green PR-level CI are useful progress, but they do not prove that the live universe is populated, the real Upstox feed is decoded correctly, reconnect gaps are repaired, the production-shaped database migrates safely, or Render runs healthy. Keep the current production service untouched until the above gates have evidence and the user explicitly approves a deployment window.

## Completion tracking

| Gate | Current evidence | Status |
|---|---|---|
| Architecture phases 1–18 integrated | PR #22 merged | Complete in repository |
| Legacy-schema migration test | PR #23 CI: 112 passed, PostgreSQL 16 | Complete in repository |
| Main-branch CI after PR #23 | Run #41 completed successfully on merge commit | Passed |
| F&O universe snapshot | Checked-in files are empty | Blocked |
| Reconnect candle-gap repair | Not implemented | Open |
| Actual Upstox V3 packet validation | Synthetic fixture only | Blocked |
| Staging DB migration + restore rehearsal | No staging DB access/evidence | Blocked |
| Render staging deployment + paper soak | No staging service/access/evidence | Blocked |
| Production release approval | Not requested or granted | Not authorized |
