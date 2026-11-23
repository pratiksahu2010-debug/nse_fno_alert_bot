# NSE F&O Intelligent Signal Alert Bot

Alert-only Python 3.11 service. It does not contain an order placement, modification, or cancellation client.

## Strategies (exactly two)

* **ORB + GAP**: uses the actual regular-session open and a completed 5/10/15-minute opening range. The default range is 15 minutes (09:15–09:30 IST); entries are completed 5-minute closes through the range boundary, cutoff 11:30 IST. A directional gap is classified at 1%, 2%, and 3%. VWAP/RVOL are optional context only.
* **Momentum Explosion**: completed 5-minute candles, EMA 9/21, ATR 14, prior 10-candle structure and either RVOL >=1.5 or candle range >=1.2 ATR. No MACD, RSI, mandatory ADX/VWAP, Supertrend, or 15-minute context. Default cutoff 15:00 IST, 30-minute per-symbol cooldown.

Both modules are independent. Coordinator preserves same-direction confluence and opposite-direction conflicts. Same-day signals from separate modules are not suppressed.

## Safety and execution model

The bot monitors underlying instruments. Entry, SL, TP1 and TP2 are underlying price levels, not option premiums. A signal is rejected when a valid structural stop cannot be calculated. Targets default to 1R and 2R. Telegram delivery uses a persistent outbox. No broker order endpoint is called anywhere in the project.

## Installation

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set `UPSTOX_ACCESS_TOKEN` (Upstox Analytics Token), Telegram credentials and `DATABASE_URL` (Neon PostgreSQL with SSL). For local isolated tests SQLite can be used, but Render deployment requires Neon.

## Upstox market data

The project uses the documented V3 authorize endpoint and a strict V3 Protobuf wire decoder. `app/market_data/protobuf_decoder.py` follows the official `MarketDataFeedV3.proto` field numbers for LTPC and full-feed packets, and ignores `market_info` packets. The WebSocket manager reconnects with exponential backoff, restores subscriptions in batches, and tracks per-instrument freshness. V3 subscription capacity is subject to the Upstox account's published limits; `/health` reports stale instruments separately from socket status. Startup warmup fetches recent 5-minute history and prior daily close; when started after the open it attempts to recover the actual 09:15 open from the current-day 1-minute API.

Historical candle APIs are V3 (`minutes/1`, etc.). Upstox V3 minute history has request-window limits; backfill callers must chunk requests rather than ask for an unlimited range.

## Frozen universe bootstrap

Run once manually with a valid token:

```bash
python scripts/bootstrap_universe.py
```

The script downloads the NSE BOD instrument master and writes `config/nse_fno_universe.json`. Review the output before committing/deploying. A production eligible F&O cash-stock list should be validated against NSE's current F&O underlying list; the Upstox BOD master is an instrument catalogue, not by itself a definitive F&O eligibility flag. The bot deliberately does not silently refresh the snapshot. To update, run the command manually, inspect the diff, then deploy the reviewed snapshot.

**Important**: The current checked-in universe file is intentionally empty. Do not deploy expecting live signals until a verified frozen universe snapshot is generated and reviewed. NIFTY/BANKNIFTY key names must be checked against the actual master output.

## Database and deployment

The app creates SQLAlchemy tables at boot for a first-run setup. SQL schema is in `app/database/migrations/0001_initial.sql`. Set Neon `DATABASE_URL` with `sslmode=require`.

Render settings:

* Build: `pip install -r requirements.txt`
* Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
* Health: `/health`

Set all variables from `.env.example` in Render. `GET /health` distinguishes DB, runtime, feed and stale-instrument health. `/ping` is keepalive only and never sends a Telegram message.

## Backtesting

`python scripts/run_backtest.py --input path/to/5m.csv --symbol RELIANCE --module MOMENTUM_EXPLOSION --out reports/` accepts OHLCV CSV with a timestamp column/index. The historical V3 API limits 1-minute interval retrieval to one-month windows; collect and archive data in chunks. Never use the same data for parameter selection and final out-of-sample reporting. The backtest engine uses conservative same-bar stop/target handling; see limitations below.

## Known limitations / production gate

* The Upstox official instrument master is a catalogue, not the authority for the current F&O eligible underlying set. Bootstrap therefore requires a separately reviewed current NSE F&O symbol list. The checked-in `config/fno_eligible_symbols.txt` is intentionally blank and `config/nse_fno_universe.json` is intentionally empty; populate/review these before deployment.
* Initial historical warmup and persisted trade lifecycle state are implemented, but automatic missing-candle backfill after a mid-session WebSocket reconnect is not yet implemented. Per-instrument staleness is exposed in `/health`; stale symbols should be treated as unavailable until repaired.
* The included V3 Protobuf decoder is covered by a synthetic schema fixture, not a capture from your live Upstox account. Validate it against an authorized account feed before enabling production alerts.
* Telegram API at-least-once delivery cannot mathematically guarantee exactly-once semantics across a process crash after Telegram accepts a message but before the DB records success. The outbox prevents duplicate concurrent leases and retries bounded failures.
* The included backtester supports both modules, chronological completed 5-minute bars, slippage, brokerage/other flat costs, conservative stop/target ambiguity, TP1/breakeven and trailing logic. Taxes/exchange charges are supplied as a configurable flat cost input rather than calculated from the latest statutory schedule; add the applicable contract-note charges for reliable net P&L.
* No strategy can guarantee win rate or profitability. Paper trade and validate out-of-sample before relying on alerts.

## Tests and verified build

```bash
pytest -q
python -m compileall -q app scripts tests
```

The delivered build was verified with **19 passing unit tests**, zero failures, Python compilation, and SQLite schema creation for all 12 ORM tables. Tests are deterministic and do not call live APIs. Neon connectivity, Upstox authorization/feed, Render deployment, and Telegram delivery were not live-tested because no credentials or account access were supplied.
