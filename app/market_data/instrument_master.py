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
        rows=self.parse(raw); chosen=[]; matched=set()
        for r in rows:
            segment=str(r.get('segment','')); instrument_type=str(r.get('instrument_type','')).upper()
            key=r.get('instrument_key'); symbol=str(r.get('trading_symbol') or r.get('name') or '').upper()
            if key and symbol and segment=='NSE_EQ' and instrument_type in {'EQ',''} and symbol in eligible:
                chosen.append({'instrument_key':key,'symbol':symbol,'name':r.get('name',symbol),'segment':segment,'instrument_type':instrument_type or 'EQ','lot_size':r.get('lot_size'),'exchange_token':r.get('exchange_token')})
                matched.add(symbol)
            if key and segment=='NSE_INDEX' and symbol in {'NIFTY','NIFTY 50','BANKNIFTY','NIFTY BANK'}:
                label='NIFTY' if symbol in {'NIFTY','NIFTY 50'} else 'BANKNIFTY'
                chosen.append({'instrument_key':key,'symbol':label,'name':r.get('name',label),'segment':segment,'instrument_type':'INDEX','lot_size':None,'exchange_token':r.get('exchange_token')})
        missing=sorted(eligible-matched)
        if missing:
            preview=', '.join(missing[:20]); suffix='...' if len(missing)>20 else ''
            raise ValueError(f'Upstox BOD master did not resolve all reviewed NSE F&O underlyings: {len(missing)} missing [{preview}{suffix}]')
        dedup={}
        for x in chosen:
            k=(x['symbol'],x['segment'])
            if k in dedup and dedup[k]['instrument_key']!=x['instrument_key']:
                raise ValueError(f"Multiple Upstox instrument keys found for {x['symbol']}")
            dedup[k]=x
        chosen=list(dedup.values())
        symbols={x['symbol'] for x in chosen}
        if not {'NIFTY','BANKNIFTY'}.issubset(symbols): raise ValueError('Both NIFTY and BANKNIFTY index records must exist in the downloaded master')
        stock_rows=[x for x in chosen if x['segment']=='NSE_EQ']
        if len(stock_rows)!=len(eligible): raise ValueError(f'Expected exactly {len(eligible)} unique NSE_EQ underlyings, found {len(stock_rows)}')
        keys=[x['instrument_key'] for x in chosen]
        if len(keys)!=len(set(keys)): raise ValueError('Duplicate instrument keys found in Upstox master matches')
        digest=hashlib.sha256(json.dumps(chosen,sort_keys=True).encode()).hexdigest()[:16]
        doc={'version':f'NSE_FNO_218_{digest}','refreshed_at':datetime.now(timezone.utc).isoformat(),'source':'Upstox complete BOD instruments JSON + reviewed NSE F&O eligible list','count':len(chosen),'stock_count':len(stock_rows),'instruments':chosen}
        Path(output).parent.mkdir(parents=True,exist_ok=True); Path(output).write_text(json.dumps(doc,indent=2)); return doc
