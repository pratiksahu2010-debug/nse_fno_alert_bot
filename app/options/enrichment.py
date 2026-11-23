from datetime import datetime,timezone

def classify_options_context(payload,asof=None,max_age_seconds=180):
    if not payload:return {"status":"UNAVAILABLE"}
    ts=payload.get("timestamp")
    if not ts:return {"status":"STALE","reason":"missing_timestamp"}
    try: stamp=datetime.fromisoformat(ts.replace("Z","+00:00"))
    except Exception:return {"status":"STALE","reason":"invalid_timestamp"}
    now=asof or datetime.now(timezone.utc)
    if (now-stamp).total_seconds()>max_age_seconds:return {"status":"STALE","timestamp":ts}
    return {"status":"AVAILABLE","timestamp":ts,"data":payload}
