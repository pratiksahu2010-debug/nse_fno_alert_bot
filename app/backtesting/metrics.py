import pandas as pd

def summarize(trades):
    if trades.empty:return {'total_trades':0,'wins':0,'losses':0,'win_rate':0.0,'gross_pnl':0.0,'net_pnl':0.0,'profit_factor':0.0,'average_rr':0.0,'max_drawdown':0.0,'average_holding_minutes':0.0}
    pnl=trades.net_pnl.astype(float); wins=pnl[pnl>0]; losses=pnl[pnl<0]; equity=pnl.cumsum(); drawdown=equity-equity.cummax()
    gross=float(trades.gross_pnl.sum()) if 'gross_pnl' in trades else float(pnl.sum())
    return {'total_trades':int(len(trades)),'wins':int(len(wins)),'losses':int(len(losses)),'win_rate':float(len(wins)/len(trades)*100),'gross_pnl':gross,'net_pnl':float(pnl.sum()),'profit_factor':float(wins.sum()/abs(losses.sum())) if len(losses) and losses.sum()!=0 else (float('inf') if len(wins) else 0.0),'average_rr':float((pnl/(trades.entry-trades.sl).abs()).mean()) if 'sl' in trades else 0.0,'max_drawdown':float(drawdown.min()),'average_holding_minutes':float(trades.holding_minutes.mean()) if 'holding_minutes' in trades else 0.0}
