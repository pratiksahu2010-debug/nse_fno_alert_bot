-- Additive event-ledger schema. Apply only through an approved migration
-- process; do not drop or rewrite existing signal_events / active_trades data.
CREATE TABLE IF NOT EXISTS domain_events (
    event_id VARCHAR(36) PRIMARY KEY,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id VARCHAR(160) NOT NULL,
    aggregate_version INTEGER NOT NULL CHECK (aggregate_version > 0),
    event_type VARCHAR(120) NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1 CHECK (schema_version > 0),
    payload JSON NOT NULL,
    idempotency_key VARCHAR(200) NOT NULL UNIQUE,
    correlation_id VARCHAR(100),
    causation_id VARCHAR(36),
    source VARCHAR(80) NOT NULL DEFAULT 'application',
    occurred_at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_domain_event_aggregate_version
        UNIQUE (aggregate_type, aggregate_id, aggregate_version)
);
CREATE INDEX IF NOT EXISTS ix_domain_events_aggregate
    ON domain_events (aggregate_type, aggregate_id, aggregate_version);
CREATE INDEX IF NOT EXISTS ix_domain_events_type_recorded
    ON domain_events (event_type, recorded_at);
CREATE INDEX IF NOT EXISTS ix_domain_events_correlation
    ON domain_events (correlation_id);
