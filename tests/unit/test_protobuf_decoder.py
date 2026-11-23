import struct
from app.market_data.protobuf_decoder import decode_market_data

def vi(n):
    out=b''
    while n>127: out+=bytes([(n&127)|128]); n>>=7
    return out+bytes([n])
def ld(n,b): return vi((n<<3)|2)+vi(len(b))+b
def fixed64(n,x): return vi((n<<3)|1)+struct.pack('<d',x)
def test_decode_v3_ltpc_tick():
    ltpc=fixed64(1,123.45)+vi(2<<3)+vi(1790000000000)+vi(3<<3)+vi(7)+fixed64(4,120.0)
    feed=ld(1,ltpc)
    entry=ld(1,b'NSE_EQ|INE000000001')+ld(2,feed)
    packet=vi(1<<3)+vi(1)+ld(2,entry)
    ticks=decode_market_data(packet)
    assert len(ticks)==1 and ticks[0].price==123.45 and ticks[0].last_qty==7
    assert ticks[0].instrument_key=='NSE_EQ|INE000000001'
