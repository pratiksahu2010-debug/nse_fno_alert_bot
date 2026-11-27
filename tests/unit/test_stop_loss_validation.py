from types import SimpleNamespace

from app.risk.stop_loss import structural_stop


def test_structural_stop_rejects_non_finite_and_non_positive_inputs():
    signal = SimpleNamespace(
        entry=100,
        direction="CALL",
        module="ORB_GAP",
        metadata={"or_low": 99, "atr": 1},
    )
    assert structural_stop(signal, float("nan")) is None
    signal.metadata["or_low"] = float("inf")
    assert structural_stop(signal, 1) is None
