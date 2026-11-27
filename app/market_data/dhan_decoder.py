"""Strict DhanHQ v2 FULL market-feed packet decoder.

Dhan's v2 feed sends little-endian binary packets. This decoder intentionally
accepts only FULL packets (response code 8), which carry LTP, LTQ, LTT and
cumulative day volume. Dhan security IDs are translated through an explicit
(segment, security_id) -> Upstox instrument_key map; IDs are never guessed.
"""
from __future__ import annotations

import math
import struct
from datetime import datetime, timezone

from .models import Tick

_FULL = struct.Struct("<BHBIfHIfIIIIIIffff100s")
_FULL_PACKET_CODE = 8


def decode_dhan_full_packet(payload: bytes, instrument_map: dict[tuple[int, str], str]):
    """Return one normalized Tick, or None for unsupported/invalid packets.

    instrument_map keys are (Dhan numeric exchange-segment code, security ID).
    The value is the canonical Upstox instrument_key used by the candle engine.
    """
    if not isinstance(payload, (bytes, bytearray, memoryview)):
        raise TypeError("Dhan feed packet must be bytes-like")
    packet = bytes(payload)
    if len(packet) < _FULL.size:
        raise ValueError(f"Truncated Dhan FULL packet: expected {_FULL.size} bytes")
    fields = _FULL.unpack_from(packet)
    code, message_length, segment, security_id = fields[:4]
    if code != _FULL_PACKET_CODE:
        return None
    if message_length < _FULL.size:
        raise ValueError("Invalid Dhan FULL packet message length")
    instrument_key = instrument_map.get((segment, str(security_id)))
    if not instrument_key:
        return None

    price = float(fields[4])
    last_qty = float(fields[5])
    traded_at = int(fields[6])
    cumulative_volume = float(fields[8])
    if not math.isfinite(price) or price <= 0:
        return None
    if traded_at <= 0:
        return None
    if not math.isfinite(cumulative_volume) or cumulative_volume < 0:
        return None
    if not math.isfinite(last_qty) or last_qty < 0:
        last_qty = None

    timestamp = datetime.fromtimestamp(traded_at, tz=timezone.utc)
    return Tick(
        instrument_key=instrument_key,
        timestamp=timestamp,
        price=price,
        cumulative_volume=cumulative_volume,
        last_qty=last_qty,
    )
