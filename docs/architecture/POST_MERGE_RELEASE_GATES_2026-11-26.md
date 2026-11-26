# Post-merge release gates — 2026-11-26

## Repository status

- Architecture integration PR #22, legacy-schema migration test PR #23, post-merge release-gate documentation PR #24, and reconnect candle-gap repair PR #25 are merged into `main`.
- PR #25 added automatic Upstox reconnect candle-gap repair before WebSocket authorization/subscription restoration, plus regression coverage for parsing, validation, merging, failure blocking and callback ordering.
- PR #25 CI passed 128 tests, Python compile checks and PostgreSQL 16 service initialization.
- Post-merge main-branch CI run #48 for commit `35abfeab75c42b40bb58588655292572bacbac12` completed successfully. The test job, dependency install, Python compile step and PostgreSQL service lifecycle all passed.
- The repository is still not approved for production release. CI validates deterministic code paths, not external credentials, live market data, or staging infrastructure.

## Hard safety invariants

1. Keep the application signal-only. No broker order placement, modification, or cancellation.
2. Keep `alert_only=true` and `order_placement_enabled=false`.
3. Preserve ORB + GAP and Momentum Explosion strategy definitions, indicator inputs, signal scoring, entry/exit behavior, risk calculations, and Telegram message contract during infrastructure hardening.
4. Keep shadow actor orchestration opt-in and separate from authoritative `LiveRuntime` startup until a separate staging parity review passes.
5. Never run schema migrations against production as part of this checklist.
6. Do not deploy, restart, or modify the production Render service without explicit approval.

## Completed repository gates

### A. Reconnect candle-gap repair — implemented and CI-verified

- Repair runs before WebSocket authorization and socket subscription restoration.
- Completed 5-minute history is fetched for each subscribed instrument; 1-minute history is repaired where microstructure history was already retained.
- Concurrent repair requests are bounded by a semaphore.
- Timestamps, interval alignment, timezone awareness, completed-bar cutoff, regular-session boundaries, OHLCV invariants and conflicting duplicates are validated.
- Historical bars merge by timestamp to repair internal holes and the tail; historical bars replace partial live bars on overlap.
- A symbol remains blocked from signal processing when repair fails and is unblocked only after a later successful repair.
- Historical repair bars rebuild indicator context but are not replayed through strategy evaluation, preventing retroactive alerts.
- Regression coverage includes malformed payloads, duplicates, ordering, merge precedence, repair failure, 1-minute history, and callback ordering.
- Remaining external verification: test against a sanitized packet/feed capture from the user's authorized Upstox account and observe a real reconnect.

### B. Automated F&O universe validation — code guard in place; external mapping still pending

- `config/fno_eligible_symbols.txt` contains 218 individual-security symbols. Its header identifies user-provided NSE `fo_mktlots.csv` and `qtyfreeze.csv` files dated 2026-11-23 as the source.
- This list has not been independently checked against the official NSE F&O eligible-underlying list for the intended release date. Perform that check before paper or production release.
- The checked-in `config/nse_fno_universe.json` is only an index-only bootstrap placeholder; it is not a usable 220-instrument production snapshot.
- Application startup downloads the Upstox NSE BOD master using `UPSTOX_ACCESS_TOKEN`, applies the reviewed symbol file as the eligibility filter, and fails closed if any symbol cannot be resolved.
- The runtime validator now requires exactly 218 unique NSE_EQ stock rows plus NIFTY and BANKNIFTY NSE_INDEX rows, unique instrument keys, and consistent metadata. An index-only bootstrap can no longer pass readiness.
- The explicit bootstrap command is `python scripts/bootstrap_universe.py`. Inspect the resulting snapshot and mapping before release.
- External blocker: no valid Analytics Token was supplied to run and verify the mapping in this session. Do not put tokens in GitHub files or logs.

### C. Live Upstox V3 protocol verification — external blocker

- Current decoder tests use synthetic schema fixtures, not a captured packet from the user's authorized Upstox account.
- Obtain a sanitized, non-secret sample from the actual V3 feed and verify LTPC, full-feed, exchange timestamps, instrument keys, market status, empty/partial packets and subscription restoration.
- Exercise a real disconnect/reconnect and confirm candle-gap repair completes before the WebSocket resumes signal processing.
- Do not put access tokens, account identifiers, or other secrets into fixtures or logs.

### D. Staging database migration and restore rehearsal — external blocker

1. Create an isolated staging database from a recent production backup or a representative sanitized copy.
2. Verify backup integrity and document restore steps before migration.
3. Inspect actual schema, migration ledger, extensions, indexes, row counts and existing signal rows.
4. Run migration adoption on staging only.
5. Verify checksums, row preservation, constraints, index validity, advisory-lock behavior and migration duration.
6. Rehearse restore from the pre-migration backup and record recovery time.
7. Never point a test or migration command at the production database.

### E. Render staging and paper-market soak — external blocker

No Render service, secret, environment variable, deployment or restart has been changed by this work. A user-controlled staging service and credentials are required.

- Confirm build/start commands and Python version.
- Set secrets only in Render's secret environment; never commit them.
- Confirm `/live`, `/ready`, `/health` and `/status` semantics.
- Verify database, validated 220-instrument universe, runtime, feed and stale-instrument counts.
- Run a paper/replay soak over normal and failure scenarios: reconnect, stale feed, delayed/out-of-order ticks, queue saturation, DB outage, restart during checkpoint, outbox retry and graceful shutdown.
- Compare emitted signals with the pre-modernization baseline and require zero order requests.
- Record CPU, memory, database pool usage, queue high-water marks, feed staleness, recovery time and outbox age.
- Verify Telegram delivery using a staging bot/chat only.

## Release decision

**Current decision: NOT PRODUCTION-READY / STAGING GATES OPEN.**

Repository code and CI are materially more complete, but the full universe has not been generated with the user's Analytics Token, current eligibility has not been independently checked against NSE's official list, the real Upstox V3 feed has not been captured/verified, and staging database/Render/paper-soak evidence is absent. Keep the production service untouched. Do not enable production alerts based only on CI.

## Completion tracking

| Gate | Current evidence | Status |
|---|---|---|
| Architecture phases 1–18 integrated | PR #22 merged | Complete in repository |
| Legacy-schema migration test | PR #23 CI passed PostgreSQL 16 | Complete in repository |
| Reconnect candle-gap repair | PR #25 merged; 128-test CI passed | Complete in repository; live verification pending |
| Main-branch CI | Run #48 passed on `35abfeab75c42b40bb58588655292572bacbac12` | Passed |
| 218-symbol source list | User-provided NSE files dated 2026-11-23 | Present; official-date cross-check pending |
| Complete 218-stock + 2-index Upstox mapping | Checked-in JSON is index-only; valid token not available here | Blocked |
| Strict universe validation/readiness | Requires 218 NSE_EQ + 2 NSE_INDEX rows | Implemented; new PR CI pending |
| Actual Upstox V3 packet + reconnect validation | Synthetic tests only | Blocked |
| Staging DB migration + restore rehearsal | No staging DB access/evidence | Blocked |
| Render staging deployment + paper soak | No staging service/access/evidence | Blocked |
| Production release approval | Not requested or granted | Not authorized |
