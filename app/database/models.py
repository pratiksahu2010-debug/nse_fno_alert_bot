from datetime import datetime,timezone
from sqlalchemy import String,Float,DateTime,Text,Integer,Boolean,ForeignKey,Index,UniqueConstraint,JSON
from sqlalchemy.orm import Mapped,mapped_column
from .connection import Base

class InstrumentRow(Base):
    __tablename__='instruments'
    instrument_key:Mapped[str]=mapped_column(String(100),primary_key=True)
    symbol:Mapped[str]=mapped_column(String(40),index=True)
    name:Mapped[str]=mapped_column(String(160)); segment:Mapped[str]=mapped_column(String(30))
    lot_size:Mapped[int|None]=mapped_column(Integer,nullable=True); exchange_token:Mapped[str|None]=mapped_column(String(40),nullable=True)
    active:Mapped[bool]=mapped_column(Boolean,default=True)

class UniverseVersionRow(Base):
    __tablename__='universe_versions'
    version:Mapped[str]=mapped_column(String(32),primary_key=True)
    refreshed_at:Mapped[datetime]=mapped_column(DateTime(timezone=True)); count:Mapped[int]=mapped_column(Integer)
    snapshot_json:Mapped[str]=mapped_column(Text)

class MarketSessionRow(Base):
    __tablename__='market_sessions'
    session_date:Mapped[datetime]=mapped_column(DateTime(timezone=True),primary_key=True)
    status:Mapped[str]=mapped_column(String(24)); open_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    close_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True); source:Mapped[str]=mapped_column(String(40),default='calendar')

class SignalRow(Base):
    __tablename__='signals'
    signal_id:Mapped[str]=mapped_column(String(32),primary_key=True)
    symbol:Mapped[str]=mapped_column(String(40),index=True); module:Mapped[str]=mapped_column(String(40),index=True)
    direction:Mapped[str]=mapped_column(String(8)); setup:Mapped[str]=mapped_column(String(40))
    timestamp:Mapped[datetime]=mapped_column(DateTime(timezone=True),index=True); entry:Mapped[float]=mapped_column(Float)
    metadata_json:Mapped[str]=mapped_column(Text,default='{}'); relation:Mapped[str]=mapped_column(String(20),default='INDEPENDENT')

class SignalEventRow(Base):
    __tablename__='signal_events'
    id:Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    signal_id:Mapped[str]=mapped_column(ForeignKey('signals.signal_id',ondelete='CASCADE'),index=True)
    event:Mapped[str]=mapped_column(String(40)); timestamp:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
    payload_json:Mapped[str]=mapped_column(Text,default='{}')

class RiskLevelRow(Base):
    __tablename__='risk_levels'
    signal_id:Mapped[str]=mapped_column(ForeignKey('signals.signal_id',ondelete='CASCADE'),primary_key=True)
    entry:Mapped[float]=mapped_column(Float); stop_loss:Mapped[float]=mapped_column(Float); target_1:Mapped[float]=mapped_column(Float); target_2:Mapped[float]=mapped_column(Float)

class TradeRow(Base):
    __tablename__='active_trades'
    signal_id:Mapped[str]=mapped_column(ForeignKey('signals.signal_id',ondelete='CASCADE'),primary_key=True)
    state_json:Mapped[str]=mapped_column(Text); updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc),onupdate=lambda:datetime.now(timezone.utc))

class OutboxRow(Base):
    __tablename__='alert_outbox'
    id:Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    alert_id:Mapped[str]=mapped_column(ForeignKey('signals.signal_id',ondelete='CASCADE'),unique=True,index=True)
    body:Mapped[str]=mapped_column(Text); status:Mapped[str]=mapped_column(String(16),default='PENDING',index=True)
    attempts:Mapped[int]=mapped_column(Integer,default=0); lease_owner:Mapped[str|None]=mapped_column(String(120),nullable=True)
    lease_until:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True); last_error:Mapped[str|None]=mapped_column(Text,nullable=True)

class AlertDeliveryRow(Base):
    __tablename__='alert_deliveries'
    id:Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    alert_id:Mapped[str]=mapped_column(ForeignKey('alert_outbox.alert_id',ondelete='CASCADE'),index=True)
    attempt:Mapped[int]=mapped_column(Integer); attempted_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
    status:Mapped[str]=mapped_column(String(16)); response_json:Mapped[str|None]=mapped_column(Text,nullable=True); error:Mapped[str|None]=mapped_column(Text,nullable=True)
    __table_args__=(UniqueConstraint('alert_id','attempt',name='uq_delivery_attempt'),)

class ModuleStateRow(Base):
    __tablename__='module_state'
    key:Mapped[str]=mapped_column(String(160),primary_key=True); value_json:Mapped[str]=mapped_column(Text)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc),onupdate=lambda:datetime.now(timezone.utc))

class SystemHealthRow(Base):
    __tablename__='system_health'
    id:Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    component:Mapped[str]=mapped_column(String(80),index=True); status:Mapped[str]=mapped_column(String(24))
    checked_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc)); details_json:Mapped[str]=mapped_column(Text,default='{}')

class BacktestRunRow(Base):
    __tablename__='backtest_runs'
    run_id:Mapped[str]=mapped_column(String(40),primary_key=True); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
    module:Mapped[str]=mapped_column(String(40)); symbol:Mapped[str]=mapped_column(String(40)); params_json:Mapped[str]=mapped_column(Text)
    metrics_json:Mapped[str]=mapped_column(Text); report_path:Mapped[str|None]=mapped_column(String(255),nullable=True)

Index('ix_signals_symbol_module_time',SignalRow.symbol,SignalRow.module,SignalRow.timestamp)
Index('ix_outbox_status_lease',OutboxRow.status,OutboxRow.lease_until)
