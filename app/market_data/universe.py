import json
from pathlib import Path


EXPECTED_FNO_STOCK_COUNT = 218
EXPECTED_INDEX_SYMBOLS = {"NIFTY", "BANKNIFTY"}


class Universe:
    def __init__(self, path):
        self.path = Path(path)
        self.data = json.loads(self.path.read_text(encoding="utf-8"))

    @property
    def instruments(self):
        return self.data["instruments"]

    def validate(self, expected_stock_count=EXPECTED_FNO_STOCK_COUNT):
        rows = self.instruments
        if not isinstance(rows, list) or not rows:
            raise ValueError("F&O universe is empty")

        keys = [row.get("instrument_key") for row in rows]
        if any(not key for key in keys) or len(keys) != len(set(keys)):
            raise ValueError("Universe has missing or duplicate instrument keys")

        stock_rows = [
            row for row in rows
            if row.get("segment") == "NSE_EQ"
            and str(row.get("instrument_type", "")).upper() in {"EQ", ""}
        ]
        stock_symbols = [str(row.get("symbol", "")).strip().upper() for row in stock_rows]
        if any(not symbol for symbol in stock_symbols):
            raise ValueError("Universe contains an NSE_EQ row with an empty symbol")
        if len(stock_symbols) != len(set(stock_symbols)):
            raise ValueError("Universe contains duplicate NSE_EQ symbols")
        if len(stock_rows) != expected_stock_count:
            raise ValueError(
                f"Expected {expected_stock_count} reviewed NSE F&O stocks; "
                f"found {len(stock_rows)}"
            )

        index_rows = [
            row for row in rows
            if row.get("segment") == "NSE_INDEX"
            and str(row.get("instrument_type", "")).upper() == "INDEX"
        ]
        index_symbols = {
            str(row.get("symbol", "")).strip().upper() for row in index_rows
        }
        if index_symbols != EXPECTED_INDEX_SYMBOLS:
            raise ValueError(
                "Universe must contain exactly NIFTY and BANKNIFTY index records"
            )

        if len(rows) != expected_stock_count + len(EXPECTED_INDEX_SYMBOLS):
            raise ValueError("Universe contains unexpected non-stock/non-index instruments")

        declared_count = self.data.get("count")
        if declared_count is not None and declared_count != len(rows):
            raise ValueError("Universe metadata count does not match instrument rows")
        declared_stocks = self.data.get("stock_count")
        if declared_stocks is not None and declared_stocks != len(stock_rows):
            raise ValueError("Universe metadata stock_count does not match NSE_EQ rows")

        return True

    @property
    def version(self):
        return self.data.get("version", "unknown")
