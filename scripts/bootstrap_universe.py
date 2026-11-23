import asyncio, argparse, os
from app.market_data.universe_bootstrap import refresh_fno_universe

async def run(eligible_file, output):
    doc = await refresh_fno_universe(os.environ['UPSTOX_ACCESS_TOKEN'], eligible_file, output)
    print(f"Saved validated snapshot {doc['version']} ({doc['stock_count']} stocks + 2 indices)")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--eligible-file', default='config/fno_eligible_symbols.txt')
    parser.add_argument('--output', default='config/nse_fno_universe.json')
    args = parser.parse_args()
    asyncio.run(run(args.eligible_file, args.output))
