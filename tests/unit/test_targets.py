from app.risk.targets import calculate_levels
def test_call_levels():
 x=calculate_levels(100,95,"CALL");assert (x["tp1"],x["tp2"])==(105,110)
