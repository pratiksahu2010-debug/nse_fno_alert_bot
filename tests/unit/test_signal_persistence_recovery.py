from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.database.connection import Base
from app.database.models import OutboxRow, SignalRow, TradeRow, RiskLevelRow
from app.runtime import LiveRuntime
from app.signals.coordinator import SignalCoordinator
from app.signals.models import Signal


def _signal(stamp=None):
    stamp = stamp or datetime.now(timezone.utc)
    return Signal.create(
        "NSE:TEST", "MOMENTUM_EXPLOSION", "CALL", "MOMENTUM_EXPANSION",
        stamp, 100.0, {"atr": 1.0, "structure_low": 95.0},
    )


def _runtime(engine):
    runtime = object.__new__(LiveRuntime)
    runtime.Session = sessionmaker(bind=engine, expire_on_commit=False)
    runtime.settings = SimpleNamespace(
        sl_atr_buffer=0.2, target_1_r=1.0, target_2_r=2.0, timezone="Asia/Kolkata"
    )
    runtime.coordinator = SignalCoordinator()
    runtime.momentum = SimpleNamespace(last_signal={})
    runtime.universe = SimpleNamespace(instruments=[{"symbol": "NSE:TEST", "instrument_key": "NSE_FO|TEST"}])
    runtime.orb_done = set()
    return runtime


def test_signal_and_alert_outbox_commit_before_memory_deduplication():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    runtime = _runtime(engine)
    candle = SimpleNamespace(high=101.0, low=99.0)

    assert LiveRuntime._persist_signal(runtime, _signal(), candle) is True
    assert len(runtime.coordinator.ids) == 1
    assert "NSE:TEST" in runtime.momentum.last_signal

    # Repeated delivery of the same completed-candle signal is suppressed.
    assert LiveRuntime._persist_signal(runtime, _signal(), candle) is False
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(SignalRow)) == 1
        assert session.scalar(select(func.count()).select_from(OutboxRow)) == 1
        assert session.scalar(select(func.count()).select_from(TradeRow)) == 1
        assert session.scalar(select(func.count()).select_from(RiskLevelRow)) == 1
    engine.dispose()


def test_failed_persistence_does_not_advance_memory_cooldown_or_dedupe(monkeypatch):
    import app.runtime as runtime_module

    class FailedRepository:
        def __init__(self, session):
            pass

        def save_with_alert(self, *args, **kwargs):
            return False

    monkeypatch.setattr(runtime_module, "SignalRepository", FailedRepository)
    runtime = _runtime(None)
    runtime.Session = lambda: _NullSession()
    signal = _signal()

    assert LiveRuntime._persist_signal(runtime, signal, SimpleNamespace(high=101.0, low=99.0)) is False
    assert runtime.coordinator.ids == set()
    assert runtime.coordinator.by_symbol_day == {}
    assert runtime.momentum.last_signal == {}


class _NullSession:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_restart_restores_latest_momentum_timestamp_and_signal_ids():
    from zoneinfo import ZoneInfo
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    today = now.date()
    first = datetime.combine(today, datetime.min.time(), tzinfo=ZoneInfo("Asia/Kolkata")).replace(hour=10)
    latest = first.replace(minute=35)
    with Session(engine) as session:
        for sid, stamp in (("older", first), ("newer", latest)):
            session.add(SignalRow(
                signal_id=sid, symbol="NSE:TEST", module="MOMENTUM_EXPLOSION",
                direction="CALL", setup="MOMENTUM_EXPANSION", timestamp=stamp,
                entry=100.0, metadata_json="{}", relation="INDEPENDENT",
            ))
        session.commit()

    runtime = _runtime(engine)
    LiveRuntime._restore_module_state(runtime)
    restored = runtime.momentum.last_signal["NSE:TEST"]
    if restored.tzinfo is None:
        restored = restored.replace(tzinfo=timezone.utc)
    assert restored == latest.astimezone(timezone.utc)
    assert runtime.coordinator.ids == {"older", "newer"}
    engine.dispose()
