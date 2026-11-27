"""Strict decoder for the Upstox MarketDataFeedV3 protobuf wire format.

Field numbers mirror Upstox's published MarketDataFeedV3.proto. Unknown fields
are skipped so additive protocol fields do not break feed ingestion.
"""
from __future__ import annotations

import math
import struct
from datetime import datetime, timezone

from .models import Tick


def _varint(buf: bytes, pos: int):
    value = 0
    shift = 0
    while pos < len(buf):
        byte = buf[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, pos
        shift += 7
        if shift > 70:
            raise ValueError("invalid protobuf varint")
    raise ValueError("truncated protobuf varint")


def _fields(buf: bytes):
    pos = 0
    while pos < len(buf):
        tag, pos = _varint(buf, pos)
        number, wire = tag >> 3, tag & 7
        if number == 0:
            raise ValueError("invalid protobuf field number")
        if wire == 0:
            value, pos = _varint(buf, pos)
        elif wire == 1:
            if pos + 8 > len(buf):
                raise ValueError("truncated fixed64")
            value = buf[pos:pos + 8]
            pos += 8
        elif wire == 2:
            size, pos = _varint(buf, pos)
            if pos + size > len(buf):
                raise ValueError("truncated length-delimited field")
            value = buf[pos:pos + size]
            pos += size
        elif wire == 5:
            if pos + 4 > len(buf):
                raise ValueError("truncated fixed32")
            value = buf[pos:pos + 4]
            pos += 4
        else:
            raise ValueError(f"unsupported protobuf wire type {wire}")
        yield number, wire, value


def _ltpc(buf):
    data = {}
    for number, wire, value in _fields(buf):
        if number in (1, 4) and wire == 1:
            data[number] = struct.unpack("<d", value)[0]
        elif number in (2, 3) and wire == 0:
            data[number] = value
    return data


def _feed(buf):
    data = {}
    for number, wire, value in _fields(buf):
        if number == 1 and wire == 2:
            data["ltpc"] = _ltpc(value)
        elif number == 2 and wire == 2:
            data["full"] = value
        elif number == 3 and wire == 2:
            data["first"] = value
    return data


def _full(buf):
    """Extract LTPC and cumulative traded volume from FullFeed."""
    data = {}
    for number, wire, value in _fields(buf):
        if number not in (1, 2) or wire != 2:
            continue
        # FullFeed oneof: marketFF=1, indexFF=2.
        for field_number, field_wire, field_value in _fields(value):
            if field_number == 1 and field_wire == 2:
                data["ltpc"] = _ltpc(field_value)
            # MarketFullFeed.vtt=6 (daily cumulative volume). IndexFullFeed
            # has no vtt field, so index volume remains unavailable.
            elif number == 1 and field_number == 6 and field_wire == 0:
                data["cumulative_volume"] = field_value
    return data


def _first_level(buf):
    """Extract LTPC and vtt from FirstLevelWithGreeks."""
    data = {}
    for number, wire, value in _fields(buf):
        if number == 1 and wire == 2:
            data["ltpc"] = _ltpc(value)
        elif number == 4 and wire == 0:
            data["cumulative_volume"] = value
    return data


def decode_market_data(payload: bytes):
    """Decode initial/live feed packets; market_info packets produce no ticks."""
    if not isinstance(payload, (bytes, bytearray)):
        raise TypeError("V3 feed must be protobuf bytes")

    packet_type = None
    feeds = []
    for number, wire, value in _fields(bytes(payload)):
        if number == 1 and wire == 0:
            packet_type = value
        elif number == 2 and wire == 2:
            key = None
            feed_value = None
            for entry_number, entry_wire, entry_value in _fields(value):
                if entry_number == 1 and entry_wire == 2:
                    key = entry_value.decode("utf-8")
                elif entry_number == 2 and entry_wire == 2:
                    feed_value = entry_value
            if key is not None and feed_value is not None:
                feeds.append((key, _feed(feed_value)))

    if packet_type == 2:  # market_info
        return []

    ticks = []
    for key, feed in feeds:
        decoded = {}
        if "ltpc" in feed:
            decoded = {"ltpc": feed["ltpc"]}
        elif "full" in feed:
            decoded = _full(feed["full"])
        elif "first" in feed:
            decoded = _first_level(feed["first"])

        ltpc = decoded.get("ltpc", {})
        price = ltpc.get(1)
        traded_at_ms = ltpc.get(2)
        if price is None or traded_at_ms is None or traded_at_ms <= 0:
            continue
        price = float(price)
        if not math.isfinite(price) or price <= 0:
            continue

        timestamp = datetime.fromtimestamp(traded_at_ms / 1000, tz=timezone.utc)
        last_qty = float(ltpc.get(3, 0))
        cumulative = decoded.get("cumulative_volume")
        if cumulative is not None:
            cumulative = float(cumulative)
            if not math.isfinite(cumulative) or cumulative < 0:
                cumulative = None
        if not math.isfinite(last_qty) or last_qty < 0:
            last_qty = None
        ticks.append(
            Tick(
                key,
                timestamp,
                price,
                cumulative_volume=cumulative,
                last_qty=last_qty,
            )
        )
    return ticks
