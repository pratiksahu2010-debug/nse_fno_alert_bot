import argparse,pandas as pd
from app.backtesting.engine import BacktestEngine
from app.backtesting.csv_export import export_reports
p=argparse.ArgumentParser(description='Chronological 5-minute OHLCV backtest')
p.add_argument('--input',required=True); p.add_argument('--symbol',required=True)
p.add_argument('--module',choices=['MOMENTUM_EXPLOSION','ORB_GAP'],default='MOMENTUM_EXPLOSION')
p.add_argument('--out',default='reports'); p.add_argument('--slippage-bps',type=float,default=5)
p.add_argument('--brokerage',type=float,default=20); p.add_argument('--other-costs',type=float,default=0)
a=p.parse_args()
df=pd.read_csv(a.input)
if 'timestamp' not in df.columns: raise SystemExit('CSV must contain timestamp,open,high,low,close,volume columns')
required={'open','high','low','close','volume'}
if not required.issubset(df.columns): raise SystemExit(f'Missing columns: {sorted(required-set(df.columns))}')
df['timestamp']=pd.to_datetime(df.timestamp,utc=True); df=df.set_index('timestamp').sort_index()
engine=BacktestEngine(slippage_bps=a.slippage_bps,brokerage_per_trade=a.brokerage,other_costs_per_trade=a.other_costs)
trades=engine.run_momentum(df,a.symbol) if a.module=='MOMENTUM_EXPLOSION' else engine.run_orb(df,a.symbol)
print(export_reports(trades,a.out))
