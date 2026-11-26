-- Additive immutable snapshot table. Apply only via an approved migration plan.
CREATE TABLE IF NOT EXISTS aggregate_snapshots (
    snapshot_id VARCHAR(36) PRIMARY KEY,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id VARCHAR(160) NOT NULL,
    aggregate_version INTEGER NOT NULL CHECK (aggregate_version > 0),
    schema_version INTEGER NOT NULL CHECK (schema_version > 0),
    state JSON NOT NULL,
    last_event_id VARCHAR(36) NOT NULL REFERENCES domain_events(event_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_aggregate_snapshot_version
        UNIQUE (aggregate_type, aggregate_id, aggregate_version)
);
CREATE INDEX IF NOT EXISTS ix_aggregate_snapshots_latest
    ON aggregate_snapshots (aggregate_type, aggregate_id, aggregate_version DESC);
