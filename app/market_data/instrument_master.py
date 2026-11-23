import gzip,json,hashlib
from pathlib import Path
from datetime import datetime,timezone
class InstrumentMaster:
    @staticmethod
    def parse(raw):
        if raw[:2]==b'\x1f\x8b': raw=gzip.decompress(raw)
        obj=json.loads(raw.decode('utf-8'))
        return obj if isinstance(obj,list) else obj.get('data',[])
    def build_snapshot(self,raw,output,eligible_symbols):
        eligible={str(x).strip().upper() for x in eligible_symbols if str(x).strip()}
        if not eligible: raise ValueError('A reviewed current NSE F&O eligible-underlying list is required; the BOD master alone is not an eligibility authority')
        rows=self.parse(raw); chosen=[]
        for r in rows:
            segment=str(r.get('segment','')); instrument_type=str(r.get('instrument_type','')).upper()
            key=r.get('instrument_key'); symbol=str(r.get('trading_symbol') or r.get('name') or '').upper()
            if key and symbol and segment=='NSE_EQ' and instrument_type in {'EQ',''} and symbol in eligible:
                chosen.append({'instrument_key':key,'symbol':symbol,'name':r.get('name',symbol),'segment':segment,'instrument_type':instrument_type or 'EQ','lot_size':r.get('lot_size'),'exchange_token':r.get('exchange_token')})
            if key and segment=='NSE_INDEX' and symbol in {'NIFTY','NIFTY 50','BANKNIFTY','NIFTY BANK'}:
                label='NIFTY' if symbol in {'NIFTY','NIFTY 50'} else 'BANKNIFTY'
                chosen.append({'instrument_key':key,'symbol':label,'name':r.get('name',label),'segment':segment,'instrument_type':'INDEX','lot_size':None,'exchange_token':r.get('exchange_token')})
        # Keep one index record per normalized index symbol.
        dedup={}
        for x in chosen: dedup[(x['symbol'],x['segment'])]=x
        chosen=list(dedup.values())
        symbols={x['symbol'] for x in chosen}
        if not {'NIFTY','BANKNIFTY'}.issubset(symbols): raise ValueError('Both NIFTY and BANKNIFTY index records must exist in the downloaded master')
        if not any(x['segment']=='NSE_EQ' for x in chosen): raise ValueError('No eligible NSE_EQ F&O underlying instruments matched the reviewed list')
        digest=hashlib.sha256(json.dumps(chosen,sort_keys=True).encode()).hexdigest()[:16]
        doc={'version':digest,'refreshed_at':datetime.now(timezone.utc).isoformat(),'source':'Upstox complete BOD instruments JSON + reviewed NSE F&O eligible list','count':len(chosen),'instruments':chosen}
        Path(output).parent.mkdir(parents=True,exist_ok=True); Path(output).write_text(json.dumps(doc,indent=2)); return doc
