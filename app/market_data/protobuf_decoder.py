"""Minimal strict decoder for Upstox MarketDataFeedV3.proto wire format.

Field numbers mirror the official Upstox V3 proto. Unknown fields are skipped safely.
"""
from __future__ import annotations
from datetime import datetime, timezone
from .models import Tick


def _varint(buf: bytes, pos: int):
    value=0; shift=0
    while pos < len(buf):
        b=buf[pos]; pos+=1; value |= (b & 0x7f) << shift
        if not b & 0x80: return value,pos
        shift += 7
        if shift > 70: raise ValueError('invalid protobuf varint')
    raise ValueError('truncated protobuf varint')


def _fields(buf: bytes):
    pos=0
    while pos < len(buf):
        tag,pos=_varint(buf,pos); number,wire=tag>>3,tag&7
        if number == 0: raise ValueError('invalid protobuf field number')
        if wire == 0: value,pos=_varint(buf,pos)
        elif wire == 1:
            if pos+8>len(buf): raise ValueError('truncated fixed64')
            value=buf[pos:pos+8]; pos+=8
        elif wire == 2:
            n,pos=_varint(buf,pos)
            if n<0 or pos+n>len(buf): raise ValueError('truncated length-delimited field')
            value=buf[pos:pos+n]; pos+=n
        elif wire == 5:
            if pos+4>len(buf): raise ValueError('truncated fixed32')
            value=buf[pos:pos+4]; pos+=4
        else: raise ValueError(f'unsupported protobuf wire type {wire}')
        yield number,wire,value


def _double(raw):
    import struct
    return struct.unpack('<d',raw)[0]


def _ltpc(buf):
    d={}
    for n,w,v in _fields(buf):
        if n in (1,4) and w==1: d[n]=_double(v)
        elif n in (2,3) and w==0: d[n]=v
    return d


def _feed(buf):
    d={}
    for n,w,v in _fields(buf):
        if n==1 and w==2: d['ltpc']=_ltpc(v)
        elif n==2 and w==2: d['full']=v
        elif n==3 and w==2: d['first']=v
    return d


def _full(buf):
    # FullFeed.oneof: marketFF=1, indexFF=2. Both contain LTPC field 1.
    for n,w,v in _fields(buf):
        if n in (1,2) and w==2:
            for fn,fw,fv in _fields(v):
                if fn==1 and fw==2: return _ltpc(fv)
    return {}


def decode_market_data(payload: bytes):
    """Return Tick objects for live_feed/initial_feed packets; market_info => []."""
    if not isinstance(payload,(bytes,bytearray)): raise TypeError('V3 feed must be protobuf bytes')
    result=[]; packet_type=None; feeds=[]
    for n,w,v in _fields(bytes(payload)):
        if n==1 and w==0: packet_type=v
        elif n==2 and w==2:
            key=None; value=None
            for en,ew,ev in _fields(v):
                if en==1 and ew==2: key=ev.decode('utf-8')
                elif en==2 and ew==2: value=ev
            if key and value: feeds.append((key,_feed(value)))
    if packet_type==2: return []
    for key,f in feeds:
        lt=f.get('ltpc') or _full(f.get('full',b''))
        if not lt or not lt.get(1): continue
        # V3 LTPC ltt is Unix epoch milliseconds, ltq is last traded quantity.
        ts=datetime.fromtimestamp(int(lt.get(2,0))/1000,tz=timezone.utc)
        price=float(lt[1]); qty=float(lt.get(3,0))
        result.append(Tick(key,ts,price,last_qty=qty))
    return result
