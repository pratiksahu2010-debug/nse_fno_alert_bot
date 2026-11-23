from datetime import datetime,timezone
from types import SimpleNamespace
from app.strategies.orb_gap import ORBGapStrategy
def test_orb_failed_gap_reversal():
 s=ORBGapStrategy(); c=SimpleNamespace(close=98,high=99,low=97,end=datetime(2026,1,1,4,45,tzinfo=timezone.utc))
 x=s.evaluate('ABC',102,100,101,99,c,c.end)
 assert x.direction=='PUT' and x.setup=='FAILED_GAP_REVERSAL'
def test_orb_no_entry_after_cutoff():
 s=ORBGapStrategy(); c=SimpleNamespace(close=102,high=103,low=101,end=datetime(2026,1,1,7,0,tzinfo=timezone.utc))
 assert s.evaluate('ABC',102,100,101,99,c,c.end) is None
