def structural_stop(signal,atr_value,buffer=0.2):
    m=signal.metadata; d=signal.direction; a=float(atr_value or m.get("atr") or 0)
    if signal.module=="ORB_GAP": level=m.get("or_low") if d=="CALL" else m.get("or_high")
    else: level=m.get("structure_low") if d=="CALL" else m.get("structure_high")
    if level is None or a<=0:return None
    sl=float(level)-buffer*a if d=="CALL" else float(level)+buffer*a
    if (d=="CALL" and sl>=signal.entry) or (d=="PUT" and sl<=signal.entry):return None
    return sl
