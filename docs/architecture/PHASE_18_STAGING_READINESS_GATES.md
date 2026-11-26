# Phase 18 — Staging readiness and integration gates

## Executive decision

**Status: NOT READY for production deployment.** The architecture work has a green CI baseline, but it is still isolated from the production `main` branch and has not been rehearsed against a staging copy of the production database or Render service.

This is a release-readiness assessment, not authorization to merge, migrate, deploy, restart, change secrets, or enable any new runtime path.

## Verified evidence

- Phase 17 PR #20 is merged into `architecture/phase-16-shadow-session-orchestration`.
- GitHub Actions run #36 on commit `705369abca5753780dc58af8730537eb5752c971` completed successfully.
- The workflow used PostgreSQL 16.16, ran `pytest -q`, and reported **111 passed in 2.02s**.
- `python -m compileall -q app scripts tests` completed successfully.
- The phase-16 architecture branch and `main` are not synchronized: GitHub compare reports `diverged`, 90 commits ahead and 1 behind, with merge base `a3702d66069ca7024732a99dda781798ffe11975`.
- Production `main` was observed at `411a73e32eb6bcde5ba74a6abe486999755f48be` during this review. No production deployment or service operation was performed.

## Release blockers

### 1. Branch integration

The architecture chain containing phases 5–17 is not yet integrated into `main`. A divergent branch comparison is not a safe release artifact. Before any deployment:
- reconcile the single behind commit and inspect all merge conflicts;
- produce a reviewed integration branch based on the current `main`;
- run the complete CI suite on that exact integration head;
- inspect the final diff against `main` to confirm strategy and signal behavior are unchanged;
- obtain explicit approval before merging to `main`.

### 2. Database migration rehearsal

The architecture branch contains versioned migrations, snapshots, projections, domain outbox and snapshot checksums. CI validates these against an ephemeral PostgreSQL 16 service; this does **not** prove compatibility with the production database.

Required staging gates:
- provision an isolated staging database with the same PostgreSQL major version and relevant extensions/settings;
- take and verify a backup before migration rehearsal;
- verify the actual schema against the migration baseline before applying migrations;
- run migration dry-run/checksum validation, then apply migrations only to staging;
- verify row counts, constraints, indexes, event ordering, projection anchors and snapshot checksums;
- rehearse restore/rollback from the backup and document recovery time;
- confirm connection pooling, lock behavior, advisory locks and migration duration under realistic load.

Do not run migrations against production as part of this phase.

### 3. Runtime integration and feature isolation

- Shadow actor recovery/session/checkpoint orchestration remains opt-in and is not connected to FastAPI or `LiveRuntime` startup.
- Keep it that way until staging proves bounded startup, recovery, backpressure, checkpoint persistence, timeout/retry and shutdown behavior under realistic tick load.
- The authoritative existing signal pipeline remains authoritative.
- No changes are authorized to strategy modules, indicators, signal scoring, entry/exit rules, risk logic, Telegram alerts or broker connectivity.
- `alert_only=true` and `order_placement_enabled=false` must be verified in staging and production before any release.

### 4. Operational readiness

Before a controlled staging soak, add or verify:
- separate liveness and readiness checks with explicit failure reasons;
- metrics for actor queue depth/drops/failures, checkpoint lag, replay duration, outbox age/retries/dead letters, DB pool saturation and feed staleness;
- structured logs with correlation IDs and instrument identifiers, without secrets or sensitive payloads;
- alerting for stale feed, failed recovery, checksum mismatch, migration drift, outbox backlog and repeated actor shutdown timeouts;
- a documented operator runbook for restart, recovery, replay audit, database restore and safe disablement.

### 5. Staging soak and acceptance

Run a staging-only soak using replayed or paper-market data, never live order placement. Acceptance should include:
- normal session start/stop and repeated start/stop;
- process crash during checkpoint write and restart recovery;
- duplicate, delayed, malformed and out-of-order ticks;
- queue saturation and slow database behavior;
- corrupted/missing snapshot and event-gap detection;
- outbox retry/dead-letter behavior;
- readiness returning unhealthy during initialization and recovering when ready;
- zero broker order requests and zero changes to emitted signal decisions compared with the baseline build.

Record test duration, tick volume, CPU/memory, DB load, queue high-water marks, checkpoint lag and recovery time.

## Explicit non-actions

This phase does not:
- merge architecture work into `main`;
- change Render service configuration, secrets, environment variables or health path;
- deploy, restart or suspend the production service;
- run production migrations or modify production data;
- enable order placement or change the alert-only mode;
- wire shadow actor orchestration into the live signal runtime.

## Exit criteria

Production readiness can be reconsidered only after branch integration is reviewed, staging migration and restore rehearsals pass, runtime isolation is demonstrated, the soak meets agreed thresholds, and the user explicitly approves the production release steps.
