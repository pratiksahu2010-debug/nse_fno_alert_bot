from datetime import datetime,timezone,timedelta

from sqlalchemy import create_engine,select,func
from sqlalchemy.orm import sessionmaker

from app.database.connection import Base
from app.database.models import AlertDeliveryRow,OutboxRow,SignalRow
from app.alerts.outbox import Outbox
from app.alerts.delivery_worker import record_delivery_failure,record_delivery_success


def make_session_factory():
    engine=create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory() as session:
        session.add(SignalRow(
            signal_id="signal-1",symbol="NIFTY",module="MOMENTUM_EXPLOSION",
            direction="CALL",setup="BREAKOUT",timestamp=datetime.now(timezone.utc),
            entry=25000.0,metadata_json="{}",relation="INDEPENDENT",
        ))
        session.add(OutboxRow(alert_id="signal-1",body="alert"))
        session.commit()
    return engine,factory


def leased(factory,lease_seconds=60):
    with factory() as session:
        row=Outbox(session).lease("worker",seconds=lease_seconds)
        return row.id,row.alert_id,row.attempts,row.lease_owner


def delivery_count(factory):
    with factory() as session:
        return session.scalar(select(func.count()).select_from(AlertDeliveryRow))


def test_success_audit_and_outbox_transition_commit_together():
    engine,factory=make_session_factory()
    try:
        row_id,alert_id,attempt,token=leased(factory)
        assert record_delivery_success(factory,row_id,alert_id,attempt,token,{"ok":True}) is True
        with factory() as session:
            row=session.get(OutboxRow,row_id)
            audit=session.scalar(select(AlertDeliveryRow).where(AlertDeliveryRow.alert_id==alert_id))
            assert row.status=="SENT"
            assert audit.status=="SENT"
            assert audit.attempt==attempt
    finally:
        engine.dispose()


def test_stale_success_does_not_write_false_sent_audit():
    engine,factory=make_session_factory()
    try:
        row_id,alert_id,attempt,old_token=leased(factory,lease_seconds=0)
        with factory() as session:
            row=session.get(OutboxRow,row_id)
            row.lease_until=datetime.now(timezone.utc)-timedelta(seconds=1)
            session.commit()
        with factory() as session:
            replacement=Outbox(session).lease("replacement",seconds=60)
            new_token=replacement.lease_owner
        assert new_token!=old_token
        assert record_delivery_success(factory,row_id,alert_id,attempt,old_token,{"ok":True}) is False
        assert delivery_count(factory)==0
        with factory() as session:
            assert session.get(OutboxRow,row_id).status=="LEASED"
    finally:
        engine.dispose()


def test_failure_audit_and_retry_transition_commit_together():
    engine,factory=make_session_factory()
    try:
        row_id,alert_id,attempt,token=leased(factory)
        assert record_delivery_failure(factory,row_id,alert_id,attempt,token,"network timeout") is True
        with factory() as session:
            row=session.get(OutboxRow,row_id)
            audit=session.scalar(select(AlertDeliveryRow).where(AlertDeliveryRow.alert_id==alert_id))
            assert row.status=="PENDING"
            assert row.last_error=="network timeout"
            assert audit.status=="FAILED"
            assert audit.error=="network timeout"
    finally:
        engine.dispose()


def test_stale_failure_does_not_write_false_failed_audit():
    engine,factory=make_session_factory()
    try:
        row_id,alert_id,attempt,old_token=leased(factory,lease_seconds=0)
        with factory() as session:
            row=session.get(OutboxRow,row_id)
            row.lease_until=datetime.now(timezone.utc)-timedelta(seconds=1)
            session.commit()
        with factory() as session:
            replacement=Outbox(session).lease("replacement",seconds=60)
            assert replacement.lease_owner!=old_token
        assert record_delivery_failure(factory,row_id,alert_id,attempt,old_token,"timeout") is False
        assert delivery_count(factory)==0
        with factory() as session:
            assert session.get(OutboxRow,row_id).status=="LEASED"
    finally:
        engine.dispose()
