# NSE F&O Intelligent Signal Alert Bot

Alert-only Python 3.11 service. It does not contain an order placement, modification, or cancellation client.

## Strategies (exactly two)

* **ORB + GAP**: uses the actual regular-session open and a completed 5/10/15-minute opening range. The default range is 15 minutes (09:15–09:30 IST); entries are completed 5-minute closes through the range boundary, cutoff 11:30 IST. A directional gap is classified at 1%, 2%, and 3%. VWAP/RVOL are optional context only.
* **Momentum Explosion**: completed 5-minute candles, EMA 9/21, ATR 14, prior 10-candle structure and either RVOL >=1.5 or candle range >=1.2 ATR. No MACD, RSI, mandatory ADX/VWAP, Supertrend, or 15-minute context. Default cutoff 15:00 IST, 30-minute per-symbol cooldown.

Both modules are independent. Coordinator preserves same-direction confluence and opposite-direction conflicts. Same-day signals from separate modules are not suppressed.

## Safety and execution model

The bot monitors underlying instruments. Entry, SL, TP1 and TP2 are underlying price levels, not option premiums. A signal is rejected when a valid structural stop cannot be calculated. Targets default to 1R and 2R. Telegram delivery uses a persistent outbox. No broker order endpoint is called anywhere in the project. The service is signal-only: it never places, modifies, or cancels orders.

## Installation

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set `UPSTOX_ACCESS_TOKEN` (Upstox Analytics Token), Telegram credentials and `DATABASE_URL` (Neon PostgreSQL with SSL). For local isolated tests SQLite can be used, but Render deployment requires Neon.

## Upstox market data and reconnect recovery

The project uses the documented V3 authorize endpoint and a strict V3 Protobuf wire decoder. `app/market_data/protobuf_decoder.py` follows the official `MarketDataFeedV3.proto` field numbers for LTPC and full-feed packets, and ignores `market_info` packets. The WebSocket manager reconnects with exponential backoff, restores subscriptions in batches, and tracks per-instrument freshness. V3 subscription capacity is subject to the Upstox account's published limits.

Before each WebSocket connection is authorized and subscriptions are restored, the runtime now performs bounded historical repair for completed 5-minute candles and, when 1-minute microstructure history is already retained, 1-minute candles. It validates timestamps, alignment, session boundaries, OHLCV and duplicates; merges by candle timestamp; and blocks a symbol from signal processing if repair fails. Repaired historical bars rebuild indicator history but are not replayed into strategies, so reconnect repair does not create retroactive alerts. This behavior is covered by automated regression tests, but still requires verification against the user's authorized live Upstox account.

Historical candle APIs are V3 (`minutes/1`, etc.). Upstox V3 minute history has request-window limits; backfill callers must chunk requests rather than ask for an unlimited range.

## F&O eligible symbols and instrument mapping

`config/fno_eligible_symbols.txt` currently contains 218 individual-security symbols. Its checked-in header records that it was assembled from user-provided NSE `fo_mktlots.csv` and `qtyfreeze.csv` files dated 2026-11-23. This is a reviewed input list, not independent proof that every symbol remains eligible for a later trading date. Before a release, cross-check it against the official NSE F&O eligible-underlying list for the intended trading date. Do not infer eligibility from the Upstox instrument master alone.

At application startup, the bot downloads the Upstox NSE BOD instrument master using `UPSTOX_ACCESS_TOKEN` and maps the reviewed 218 symbols to their NSE_EQ instrument keys, plus NIFTY and BANKNIFTY index keys. Startup fails closed if the token is missing, any reviewed symbol cannot be resolved, or the resulting universe fails strict validation. The validated snapshot is written to `UNIVERSE_PATH` (default `config/nse_fno_universe.json`). The Upstox BOD file is an instrument catalogue, not the source of F&O eligibility; the reviewed symbol file remains the eligibility filter.

You can run the same bootstrap explicitly to inspect the generated mapping before committing a reviewed snapshot:

```bash
python scripts/bootstrap_universe.py
```

The runtime validator requires exactly 218 unique NSE_EQ stocks plus the two required NSE_INDEX records, with unique instrument keys and consistent snapshot metadata. The checked-in `config/nse_fno_universe.json` is currently an index-only bootstrap placeholder; it is not a valid production universe and must not be used as evidence of successful stock mapping. The runtime must regenerate and validate the complete mapping before starting.

## Database and deployment

Database schema is managed by ordered, checksummed PostgreSQL migrations in `app/database/migrations/`. Before starting a new deployment or applying a schema update, run `python -m scripts.migrate` with the intended Neon `DATABASE_URL` (SSL required). App startup only verifies the migration ledger and refuses to initialize the trading runtime if migrations are missing or have changed. It does not run DDL automatically.

Render settings:

* Build: `pip install -r requirements.txt`
* Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
* Health: `/health`
* Readiness: `/ready`
* Liveness: `/live`

Set all variables from `.env.example` in Render. `/ready` returns HTTP 503 until the database, runtime, full validated universe, and feed are ready. `/health` reports database, runtime, feed and stale-instrument details. `/ping` is keepalive only and never sends a Telegram message.

## Backtesting

`python scripts/run_backtest.py --input path/to/5m.csv --symbol RELIANCE --module MOMENTUM_EXPLOSION --out reports/` accepts OHLCV CSV with a timestamp column/index. The historical V3 API limits 1-minute interval retrieval to one-month windows; collect and archive data in chunks. Never use the same data for parameter selection and final out-of-sample reporting. The backtest engine uses conservative same-bar stop/target handling; see limitations below.

## Known limitations / production gate

* The 218-symbol eligibility file is based on user-provided NSE files dated 2026-11-23 and must be checked against the official current NSE eligible-underlying list for the intended trading date.
* The checked-in instrument mapping is only an index placeholder. A valid Upstox Analytics Token and a successful BOD mapping run are required to generate the complete 218-stock + 2-index universe. This has not been live-verified in this repository session.
* The V3 Protobuf decoder and reconnect repair have synthetic/regression test coverage, not a sanitized packet capture from the user's authorized live Upstox account. Validate LTPC, full-feed, exchange timestamps, subscriptions and repair against that account before enabling production alerts.
* CI uses ephemeral PostgreSQL 16. An isolated Neon staging database migration/restore rehearsal has not been performed.
* No Render staging deployment, paper-market soak, or Telegram live-delivery validation has been performed in this work. No Render service, secret, environment variable, deployment or restart was changed.
* Telegram API at-least-once delivery cannot mathematically guarantee exactly-once semantics across a process crash after Telegram accepts a message but before the DB records success. The outbox prevents duplicate concurrent leases and retries bounded failures.
* The included backtester supports both modules, chronological completed 5-minute bars, slippage, brokerage/other flat costs, conservative stop/target ambiguity, TP1/breakeven and trailing logic. Taxes/exchange charges are supplied as a configurable flat cost input rather than calculated from the latest statutory schedule; add the applicable contract-note charges for reliable net P&L.
* No strategy can guarantee win rate or profitability. Paper trade and validate out-of-sample before relying on alerts.

See [Post-merge release gates](docs/architecture/POST_MERGE_RELEASE_GATES_2026-11-26.md) for current status and the staging-only acceptance checklist.

## Tests and verified build

```bash
pytest -q
python -m compileall -q app scripts tests
```

PR #25 merged the automatic reconnect candle-gap repair. Its PR CI passed 128 tests, Python compile checks and PostgreSQL 16 service initialization. The post-merge main-branch CI run #48 for commit `35abfeab75c42b40bb58588655292572bacbac12` also completed successfully: all test and compile steps passed.

Tests are deterministic and do not call live APIs. Neon connectivity, Upstox authorization/feed, Render deployment, and Telegram delivery have not been live-tested because no credentials or staging account access were supplied. Do not infer production readiness from CI alone.
