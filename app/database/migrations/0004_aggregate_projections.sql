-- Additive CQRS read-model table; apply only after the event-ledger migrations.
CREATE TABLE IF NOT EXISTS aggregate_projections (
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id VARCHAR(160) NOT NULL,
    aggregate_version INTEGER NOT NULL CHECK (aggregate_version > 0),
    state JSON NOT NULL,
    last_event_id VARCHAR(36) NOT NULL REFERENCES domain_events(event_id),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (aggregate_type, aggregate_id)
);
CREATE INDEX IF NOT EXISTS ix_aggregate_projections_version
    ON aggregate_projections (aggregate_type, aggregate_version);
