from datetime import datetime, timezone
from types import SimpleNamespace

from app.strategies.orb_gap import ORBGapStrategy


def test_orb_failed_gap_reversal_and_quality_metadata():
    strategy = ORBGapStrategy()
    candle = SimpleNamespace(open=99, close=98, high=99, low=97, end=datetime(2026, 1, 1, 4, 45, tzinfo=timezone.utc))
    signal = strategy.evaluate("ABC", 102, 100, 101, 99, candle, candle.end, vwap=99, rvol=2.0)
    assert signal.direction == "PUT" and signal.setup == "FAILED_GAP_REVERSAL"
    assert signal.metadata["orb_quality_score"] == 70
    assert signal.metadata["orb_volume_confirmed"] is True


def test_orb_quality_score_marks_missing_confirmations_as_unknown():
    strategy = ORBGapStrategy()
    candle = SimpleNamespace(open=100, close=102, high=103, low=99, end=datetime(2026, 1, 1, 4, 45, tzinfo=timezone.utc))
    signal = strategy.evaluate("ABC", 100, 100, 101, 99, candle, candle.end)
    assert signal.metadata["orb_quality_score"] == 55
    assert signal.metadata["orb_vwap_aligned"] is None
    assert signal.metadata["orb_volume_confirmed"] is None
