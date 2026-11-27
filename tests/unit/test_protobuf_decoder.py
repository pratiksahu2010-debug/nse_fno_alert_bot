import struct

from app.market_data.protobuf_decoder import decode_market_data


def vi(number):
    output = b""
    while number > 127:
        output += bytes([(number & 127) | 128])
        number >>= 7
    return output + bytes([number])


def ld(number, value):
    return vi((number << 3) | 2) + vi(len(value)) + value


def fixed64(number, value):
    return vi((number << 3) | 1) + struct.pack("<d", value)


def varint_field(number, value):
    return vi(number << 3) + vi(value)


def ltpc(price=123.45, timestamp=1790000000000, quantity=7):
    return (
        fixed64(1, price)
        + varint_field(2, timestamp)
        + varint_field(3, quantity)
        + fixed64(4, 120.0)
    )


def packet_for_feed(feed, packet_type=1, key=b"NSE_EQ|INE000000001"):
    entry = ld(1, key) + ld(2, feed)
    return varint_field(1, packet_type) + ld(2, entry)


def test_decode_v3_ltpc_tick():
    ticks = decode_market_data(packet_for_feed(ld(1, ltpc())))
    assert len(ticks) == 1
    assert ticks[0].price == 123.45
    assert ticks[0].last_qty == 7
    assert ticks[0].cumulative_volume is None
    assert ticks[0].instrument_key == "NSE_EQ|INE000000001"


def test_decode_market_full_feed_vtt_and_ltpc():
    market_full_feed = ld(1, ltpc()) + varint_field(6, 123456)
    full_feed = ld(1, market_full_feed)  # FullFeed.marketFF
    feed = ld(2, full_feed)  # Feed.fullFeed
    tick = decode_market_data(packet_for_feed(feed))[0]
    assert tick.price == 123.45
    assert tick.last_qty == 7
    assert tick.cumulative_volume == 123456


def test_decode_index_full_feed_without_volume_counter():
    index_full_feed = ld(1, ltpc())
    full_feed = ld(2, index_full_feed)  # FullFeed.indexFF
    tick = decode_market_data(packet_for_feed(ld(2, full_feed)))[0]
    assert tick.cumulative_volume is None


def test_decode_first_level_with_greeks_vtt():
    first_level = ld(1, ltpc()) + varint_field(4, 9876)
    tick = decode_market_data(packet_for_feed(ld(3, first_level)))[0]
    assert tick.cumulative_volume == 9876


def test_initial_feed_is_decoded_and_market_info_is_ignored():
    assert len(decode_market_data(packet_for_feed(ld(1, ltpc()), packet_type=0))) == 1
    market_info = varint_field(1, 2)
    assert decode_market_data(market_info) == []


def test_missing_or_invalid_exchange_timestamp_and_price_are_ignored():
    no_timestamp = fixed64(1, 123.45)
    invalid_price = fixed64(1, float("nan")) + varint_field(2, 1790000000000)
    assert decode_market_data(packet_for_feed(ld(1, no_timestamp))) == []
    assert decode_market_data(packet_for_feed(ld(1, invalid_price))) == []
