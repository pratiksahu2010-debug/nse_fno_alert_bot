from math import isfinite


def calculate_levels(entry, sl, direction, tp1_r=1.0, tp2_r=2.0):
    try:
        entry, sl, tp1_r, tp2_r = map(float, (entry, sl, tp1_r, tp2_r))
    except (TypeError, ValueError, OverflowError):
        raise ValueError("entry, stop and reward/risk multipliers must be finite numbers")
    if not all(isfinite(value) for value in (entry, sl, tp1_r, tp2_r)):
        raise ValueError("entry, stop and reward/risk multipliers must be finite numbers")
    if entry <= 0 or sl <= 0 or tp1_r <= 0 or tp2_r <= 0 or tp2_r < tp1_r:
        raise ValueError("entry, stop and reward/risk multipliers must be positive and ordered")
    risk = abs(entry - sl)
    if risk <= 0:
        raise ValueError("stop loss must differ from entry")
    if direction == "CALL":
        tp1 = entry + risk * tp1_r
        tp2 = entry + risk * tp2_r
    elif direction == "PUT":
        tp1 = entry - risk * tp1_r
        tp2 = entry - risk * tp2_r
    else:
        raise ValueError("direction must be CALL or PUT")
    if direction == "CALL" and not sl < entry < tp1 < tp2:
        raise ValueError("invalid CALL level ordering")
    if direction == "PUT" and not sl > entry > tp1 > tp2:
        raise ValueError("invalid PUT level ordering")
    return {"entry": entry, "sl": sl, "tp1": float(tp1), "tp2": float(tp2), "risk": risk, "rr": tp2_r}
