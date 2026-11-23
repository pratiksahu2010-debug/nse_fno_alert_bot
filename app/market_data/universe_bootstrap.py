"""Build and validate the frozen NSE F&O underlying snapshot from the reviewed list."""
from pathlib import Path
from .upstox_client import UpstoxClient
from .instrument_master import InstrumentMaster

async def refresh_fno_universe(token: str, eligible_file: str, output_file: str) -> dict:
    eligible_path = Path(eligible_file)
    if not eligible_path.is_file():
        raise FileNotFoundError(f"Reviewed F&O eligible-symbol file not found: {eligible_path}")
    eligible = [
        line.strip().upper()
        for line in eligible_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if len(eligible) != len(set(eligible)):
        raise ValueError("Reviewed F&O eligible-symbol file contains duplicate symbols")
    if len(eligible) != 218:
        raise ValueError(f"Expected 218 reviewed stock symbols; found {len(eligible)}")
    client = UpstoxClient(token)
    try:
        raw = await client.instrument_master("NSE")
        return InstrumentMaster().build_snapshot(raw, output_file, eligible)
    finally:
        await client.close()
