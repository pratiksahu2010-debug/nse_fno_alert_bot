from app.risk.targets import calculate_levels
def test_call_levels():
 x=calculate_levels(100,95,"CALL");assert (x["tp1"],x["tp2"])==(105,110)



def test_invalid_non_finite_risk_inputs_are_rejected():
    import pytest
    with pytest.raises(ValueError):
        calculate_levels(float("nan"), 95, "CALL")
    with pytest.raises(ValueError):
        calculate_levels(100, 95, "CALL", tp1_r=2, tp2_r=1)
