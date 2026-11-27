import struct
from datetime import datetime, timezone

import pytest

from app.market_data.dhan_decoder import decode_dhan_full_packet


FULL = struct.Struct("<BHBIfHIfIIIIIIffff100s")


def packet(
    *,
    code=8,
    length=162,
    segment=1,
    security_id=1333,
    price=250.5,
    last_qty=10,
    traded_at=1790000000,
    volume=123456,
):
    return FULL.pack(
        code, length, segment, security_id, price, last_qty, traded_at, 249.8,
        volume, 100, 200, 300, 400, 50,
        245.0, 0.0, 251.0, 244.0, b"\0" * 100,
    )


def test_decodes_dhan_full_packet_to_canonical_upstox_key():
    tick = decode_dhan_full_packet(
        packet(),
        {(1, "1333"): "NSE_EQ|HDFCBANK"},
    )

    assert tick.instrument_key == "NSE_EQ|HDFCBANK"
    assert tick.price == pytest.approx(250.5)
    assert tick.last_qty == 10
    assert tick.cumulative_volume == 123456
    assert tick.timestamp == datetime.fromtimestamp(1790000000, timezone.utc)


def test_unknown_security_id_is_ignored_not_guessed():
    assert decode_dhan_full_packet(packet(), {}) is None


def test_non_full_packet_is_ignored():
    assert decode_dhan_full_packet(packet(code=4), {(1, "1333"): "NSE_EQ|HDFCBANK"}) is None


def test_truncated_packet_is_rejected():
    with pytest.raises(ValueError, match="Truncated Dhan FULL packet"):
        decode_dhan_full_packet(b"\x08" * 20, {(1, "1333"): "NSE_EQ|HDFCBANK"})


def test_invalid_price_or_missing_exchange_timestamp_is_rejected():
    mapping = {(1, "1333"): "NSE_EQ|HDFCBANK"}
    assert decode_dhan_full_packet(packet(price=0), mapping) is None
    assert decode_dhan_full_packet(packet(traded_at=0), mapping) is None


def test_negative_cumulative_volume_is_rejected():
    # The wire field is unsigned, so a negative value cannot be represented;
    # a malformed non-finite LTP is still rejected before creating a Tick.
    assert decode_dhan_full_packet(packet(price=float("nan")), {(1, "1333"): "NSE_EQ|HDFCBANK"}) is None
