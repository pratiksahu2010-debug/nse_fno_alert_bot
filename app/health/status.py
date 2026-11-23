from datetime import datetime,timezone

def status_snapshot(connected,universe_count,last_tick,db_ok):return {"ok":bool(db_ok),"service":"nse-fno-alert-bot","market_data_connected":bool(connected),"universe_count":universe_count,"last_tick_utc":last_tick.isoformat() if last_tick else None,"database_ok":bool(db_ok),"timestamp":datetime.now(timezone.utc).isoformat(),"order_placement":False}
