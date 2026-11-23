from zoneinfo import ZoneInfo
IST=ZoneInfo("Asia/Kolkata")
def format_signal(signal,levels,options=None):
    d=signal.direction
    if d=="CALL" and not (levels["sl"]<levels["entry"]<levels["tp1"]<=levels["tp2"]):raise ValueError("Invalid CALL price ordering")
    if d=="PUT" and not (levels["sl"]>levels["entry"]>levels["tp1"]>=levels["tp2"]):raise ValueError("Invalid PUT price ordering")
    stamp=signal.timestamp.astimezone(IST).strftime("%d-%b-%Y %H:%M IST")
    marker="🟢" if d=="CALL" else "🔴"
    opt=options or {"status":"UNAVAILABLE"}
    return (f"{marker} {signal.symbol} — {signal.module.replace('_',' ')} {d}\nSetup: {signal.setup}\nTime: {stamp}\n\nUnderlying levels (not option premium):\nEntry: ₹{levels['entry']:.2f} | SL: ₹{levels['sl']:.2f} | TP1: ₹{levels['tp1']:.2f} | TP2: ₹{levels['tp2']:.2f}\nRisk/Reward: 1:{levels['rr']:.2f}\nOptions context: {opt.get('status','UNAVAILABLE')}\nModule: {signal.module} | Relation: {signal.relation}\nAlert only — no order has been placed.")
