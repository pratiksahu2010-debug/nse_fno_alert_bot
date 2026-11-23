def ratchet_stop(direction,current_stop,candidate,entry):
    if direction=="CALL": return max(current_stop,entry,candidate)
    return min(current_stop,entry,candidate)
