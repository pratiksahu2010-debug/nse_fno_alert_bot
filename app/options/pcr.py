def pcr(put_oi,call_oi):
    if call_oi is None or call_oi<=0 or put_oi is None:return None
    return float(put_oi)/float(call_oi)
