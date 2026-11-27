import pytest

from app.market_data.dhan_instrument_master import build_dhan_instrument_map


HEADER = (
    "SEM_EXM_EXCH_ID,SEM_SEGMENT,SEM_SMST_SECURITY_ID,"
    "SEM_INSTRUMENT_NAME,SEM_TRADING_SYMBOL\n"
)


def universe():
    return [
        {"instrument_key": "NSE_EQ|HDFCBANK", "symbol": "HDFCBANK", "segment": "NSE_EQ"},
        {"instrument_key": "NSE_EQ|RELIANCE", "symbol": "RELIANCE", "segment": "NSE_EQ"},
        {"instrument_key": "NSE_INDEX|Nifty 50", "symbol": "NIFTY", "segment": "NSE_INDEX"},
        {"instrument_key": "NSE_INDEX|Nifty Bank", "symbol": "BANKNIFTY", "segment": "NSE_INDEX"},
    ]


def test_builds_explicit_dhan_to_canonical_map():
    csv = HEADER + (
        "NSE,E,1333,EQUITY,HDFCBANK\n"
        "NSE,E,2885,EQUITY,RELIANCE-EQ\n"
        "NSE,I,13,INDEX,NIFTY\n"
        "NSE,I,25,INDEX,BANKNIFTY\n"
        "NSE,D,49081,OPTSTK,HDFCBANK\n"
        "BSE,E,532540,EQUITY,HDFCBANK\n"
    )
    result = build_dhan_instrument_map(csv, universe())
    assert result == {
        (1, "1333"): "NSE_EQ|HDFCBANK",
        (1, "2885"): "NSE_EQ|RELIANCE",
        (0, "13"): "NSE_INDEX|Nifty 50",
        (0, "25"): "NSE_INDEX|Nifty Bank",
    }


def test_missing_canonical_symbol_fails_closed():
    csv = HEADER + "NSE,E,1333,EQUITY,HDFCBANK\n"
    with pytest.raises(ValueError, match="did not resolve"):
        build_dhan_instrument_map(csv, universe())


def test_ambiguous_ids_for_same_symbol_fail_closed():
    csv = HEADER + (
        "NSE,E,1333,EQUITY,HDFCBANK\n"
        "NSE,E,9999,EQUITY,HDFCBANK\n"
        "NSE,E,2885,EQUITY,RELIANCE\n"
        "NSE,I,13,INDEX,NIFTY\n"
        "NSE,I,25,INDEX,BANKNIFTY\n"
    )
    with pytest.raises(ValueError, match="ambiguous security IDs"):
        build_dhan_instrument_map(csv, universe())


def test_missing_columns_fail_closed():
    with pytest.raises(ValueError, match="missing columns"):
        build_dhan_instrument_map("symbol,id\nHDFCBANK,1333\n", universe())


def test_duplicate_dhan_security_id_across_symbols_fails_closed():
    csv = HEADER + (
        "NSE,E,1333,EQUITY,HDFCBANK\n"
        "NSE,E,1333,EQUITY,RELIANCE\n"
        "NSE,I,13,INDEX,NIFTY\n"
        "NSE,I,25,INDEX,BANKNIFTY\n"
    )
    with pytest.raises(ValueError, match="reused"):
        build_dhan_instrument_map(csv, universe())
