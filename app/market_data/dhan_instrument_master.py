"""Strict Dhan security-master mapping to the canonical Upstox universe.

The public Dhan CSV is an identifier source only. Strategy symbols and canonical
instrument keys remain owned by the validated Upstox universe; no IDs are
inferred from symbol spelling or hardcoded.
"""
from __future__ import annotations

import csv
import io
from collections import defaultdict
from typing import Iterable


# DhanHQ v2 feed exchange-segment numeric codes (not CSV segment letters).
DHAN_SEGMENT_CODES = {"IDX_I": 0, "NSE_EQ": 1}


def _symbol(value: object) -> str:
    symbol = str(value or "").strip().upper()
    if symbol.endswith("-EQ"):
        symbol = symbol[:-3]
    return symbol


def build_dhan_instrument_map(
    raw_csv: str | bytes,
    canonical_instruments: Iterable[dict],
) -> dict[tuple[int, str], str]:
    """Build (Dhan feed segment code, Dhan security ID) -> canonical key.

    Requires an exact, unique Dhan master match for every canonical NSE_EQ
    stock and NSE_INDEX index. The Dhan CSV's NSE:E and NSE:I rows are used;
    derivatives and all other exchanges are deliberately excluded.
    """
    if isinstance(raw_csv, bytes):
        raw_csv = raw_csv.decode("utf-8-sig")
    if not isinstance(raw_csv, str) or not raw_csv.strip():
        raise ValueError("Dhan security master CSV is empty")
    reader = csv.DictReader(io.StringIO(raw_csv))
    required = {
        "SEM_EXM_EXCH_ID",
        "SEM_SEGMENT",
        "SEM_SMST_SECURITY_ID",
        "SEM_INSTRUMENT_NAME",
        "SEM_TRADING_SYMBOL",
    }
    headers = set(reader.fieldnames or [])
    missing_headers = sorted(required - headers)
    if missing_headers:
        raise ValueError(f"Dhan security master missing columns: {', '.join(missing_headers)}")

    desired: dict[tuple[str, str], str] = {}
    for row in canonical_instruments:
        key = str(row.get("instrument_key") or "").strip()
        segment = str(row.get("segment") or "").strip()
        symbol = _symbol(row.get("symbol"))
        if not key or not symbol:
            raise ValueError("Canonical universe contains an empty instrument key or symbol")
        if segment == "NSE_EQ":
            identity = ("NSE_EQ", symbol)
        elif segment == "NSE_INDEX":
            identity = ("IDX_I", symbol)
        else:
            continue
        if identity in desired and desired[identity] != key:
            raise ValueError(f"Canonical universe has duplicate identity: {identity}")
        desired[identity] = key

    if not desired:
        raise ValueError("Canonical universe contains no NSE_EQ or NSE_INDEX instruments")

    candidates: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in reader:
        exchange = str(row.get("SEM_EXM_EXCH_ID") or "").strip().upper()
        csv_segment = str(row.get("SEM_SEGMENT") or "").strip().upper()
        instrument_type = str(row.get("SEM_INSTRUMENT_NAME") or "").strip().upper()
        security_id = str(row.get("SEM_SMST_SECURITY_ID") or "").strip()
        symbol = _symbol(row.get("SEM_TRADING_SYMBOL"))
        if exchange != "NSE" or not security_id or not symbol:
            continue
        if csv_segment == "E" and instrument_type == "EQUITY":
            identity = ("NSE_EQ", symbol)
        elif csv_segment == "I" and instrument_type == "INDEX":
            identity = ("IDX_I", symbol)
        else:
            continue
        if identity in desired:
            candidates[identity].add(security_id)

    result: dict[tuple[int, str], str] = {}
    missing: list[str] = []
    for identity, canonical_key in desired.items():
        ids = candidates.get(identity, set())
        if not ids:
            missing.append(f"{identity[0]}:{identity[1]}")
            continue
        if len(ids) != 1:
            raise ValueError(f"Dhan master has ambiguous security IDs for {identity}: {sorted(ids)}")
        feed_segment = DHAN_SEGMENT_CODES[identity[0]]
        security_id = next(iter(ids))
        map_key = (feed_segment, security_id)
        if map_key in result:
            raise ValueError(f"Dhan security ID is reused across canonical instruments: {map_key}")
        result[map_key] = canonical_key

    if missing:
        preview = ", ".join(sorted(missing)[:20])
        suffix = "..." if len(missing) > 20 else ""
        raise ValueError(f"Dhan master did not resolve {len(missing)} canonical instruments: {preview}{suffix}")
    if len(result) != len(desired):
        raise ValueError("Dhan security map is incomplete")
    return result
