import asyncio,os,argparse
from pathlib import Path
from app.market_data.upstox_client import UpstoxClient
from app.market_data.instrument_master import InstrumentMaster
async def run(eligible_file,output):
 symbols=[x.strip().upper() for x in Path(eligible_file).read_text().splitlines() if x.strip() and not x.startswith('#')]
 c=UpstoxClient(os.environ['UPSTOX_ACCESS_TOKEN'])
 try:
  raw=await c.instrument_master('NSE'); doc=InstrumentMaster().build_snapshot(raw,output,symbols)
  print(f"Saved frozen snapshot {doc['version']} ({doc['count']} instruments)")
 finally: await c.close()
if __name__=='__main__':
 p=argparse.ArgumentParser(); p.add_argument('--eligible-file',default='config/fno_eligible_symbols.txt'); p.add_argument('--output',default='config/nse_fno_universe.json'); a=p.parse_args(); asyncio.run(run(a.eligible_file,a.output))
