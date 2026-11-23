from pathlib import Path
from .metrics import summarize

def export_reports(trades,outdir):
    p=Path(outdir);p.mkdir(parents=True,exist_ok=True);trades.to_csv(p/"trades.csv",index=False)
    summary=summarize(trades);__import__('pandas').DataFrame([summary]).to_csv(p/"strategy_summary.csv",index=False)
    (trades.groupby("symbol").net_pnl.agg(["count","sum","mean"]).reset_index().to_csv(p/"symbol_summary.csv",index=False) if not trades.empty else __import__('pandas').DataFrame().to_csv(p/"symbol_summary.csv",index=False))
    if not trades.empty:
        x=trades.copy();x["month"]=__import__('pandas').to_datetime(x.timestamp).dt.to_period("M").astype(str);x.groupby("month").net_pnl.agg(["count","sum"]).reset_index().to_csv(p/"monthly_summary.csv",index=False)
    else: __import__('pandas').DataFrame().to_csv(p/"monthly_summary.csv",index=False)
    return summary
