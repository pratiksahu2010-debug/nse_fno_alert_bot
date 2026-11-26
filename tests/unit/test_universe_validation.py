import json

import pytest

from app.market_data.universe import Universe


def make_snapshot(stock_count=218):
    rows = [
        {
            "instrument_key": f"NSE_EQ|{index:03d}",
            "symbol": f"STOCK{index:03d}",
            "segment": "NSE_EQ",
            "instrument_type": "EQ",
        }
        for index in range(stock_count)
    ]
    rows.extend(
        [
            {
                "instrument_key": "NSE_INDEX|Nifty 50",
                "symbol": "NIFTY",
                "segment": "NSE_INDEX",
                "instrument_type": "INDEX",
            },
            {
                "instrument_key": "NSE_INDEX|Nifty Bank",
                "symbol": "BANKNIFTY",
                "segment": "NSE_INDEX",
                "instrument_type": "INDEX",
            },
        ]
    )
    return {
        "version": "NSE_FNO_218_TEST",
        "count": len(rows),
        "stock_count": stock_count,
        "instruments": rows,
    }


def write_snapshot(tmp_path, document):
    path = tmp_path / "universe.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_universe_accepts_exact_reviewed_stock_and_index_count(tmp_path):
    universe = Universe(write_snapshot(tmp_path, make_snapshot()))

    assert universe.validate() is True
    assert len(universe.instruments) == 220
    assert universe.version == "NSE_FNO_218_TEST"


def test_universe_rejects_index_only_bootstrap(tmp_path):
    document = make_snapshot(stock_count=0)
    with pytest.raises(ValueError, match="Expected 218 reviewed NSE F&O stocks"):
        Universe(write_snapshot(tmp_path, document)).validate()


def test_universe_rejects_missing_stock(tmp_path):
    document = make_snapshot()
    document["instruments"] = document["instruments"][:-3] + document["instruments"][-2:]
    document["count"] = len(document["instruments"])
    document["stock_count"] = 217

    with pytest.raises(ValueError, match="Expected 218 reviewed NSE F&O stocks"):
        Universe(write_snapshot(tmp_path, document)).validate()


def test_universe_rejects_missing_index(tmp_path):
    document = make_snapshot()
    document["instruments"] = document["instruments"][:-1]
    document["count"] = len(document["instruments"])
    document["stock_count"] = 218

    with pytest.raises(ValueError, match="exactly NIFTY and BANKNIFTY"):
        Universe(write_snapshot(tmp_path, document)).validate()


def test_universe_rejects_duplicate_keys_and_symbols(tmp_path):
    document = make_snapshot()
    document["instruments"][1]["instrument_key"] = document["instruments"][0]["instrument_key"]

    with pytest.raises(ValueError, match="missing or duplicate instrument keys"):
        Universe(write_snapshot(tmp_path, document)).validate()

    document = make_snapshot()
    document["instruments"][1]["symbol"] = document["instruments"][0]["symbol"]

    with pytest.raises(ValueError, match="duplicate NSE_EQ symbols"):
        Universe(write_snapshot(tmp_path, document)).validate()


def test_universe_rejects_mismatched_snapshot_metadata(tmp_path):
    document = make_snapshot()
    document["count"] -= 1

    with pytest.raises(ValueError, match="metadata count"):
        Universe(write_snapshot(tmp_path, document)).validate()
