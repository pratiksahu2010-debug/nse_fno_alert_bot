import json
import pytest
from app.market_data.instrument_master import InstrumentMaster

def test_snapshot_filters_only_reviewed_eligible_equities(tmp_path):
    rows=[
      {'segment':'NSE_EQ','instrument_type':'EQ','instrument_key':'NSE_EQ|AAA','trading_symbol':'AAA','name':'AAA LTD','lot_size':1},
      {'segment':'NSE_EQ','instrument_type':'EQ','instrument_key':'NSE_EQ|BBB','trading_symbol':'BBB','name':'BBB LTD','lot_size':1},
      {'segment':'NSE_INDEX','instrument_type':'INDEX','instrument_key':'NSE_INDEX|Nifty 50','trading_symbol':'Nifty 50','name':'Nifty 50'},
      {'segment':'NSE_INDEX','instrument_type':'INDEX','instrument_key':'NSE_INDEX|Nifty Bank','trading_symbol':'Nifty Bank','name':'Nifty Bank'},
    ]
    out=tmp_path/'universe.json'
    doc=InstrumentMaster().build_snapshot(json.dumps(rows).encode(),out,['AAA'])
    assert doc['count']==3 and {x['symbol'] for x in doc['instruments']}=={'AAA','NIFTY','BANKNIFTY'}
def test_snapshot_requires_reviewed_fo_list(tmp_path):
    with pytest.raises(ValueError): InstrumentMaster().build_snapshot(b'[]',tmp_path/'x.json',[])
