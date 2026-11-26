-- Durable domain event delivery intent; distinct from Telegram alert_outbox.
CREATE TABLE IF NOT EXISTS domain_outbox (
    outbox_id VARCHAR(36) PRIMARY KEY,
    event_id VARCHAR(36) NOT NULL REFERENCES domain_events(event_id),
    destination VARCHAR(120) NOT NULL,
    payload JSON NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'PENDING',
    attempts INTEGER NOT NULL DEFAULT 0,
    available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    lease_owner VARCHAR(120),
    lease_until TIMESTAMPTZ,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_domain_outbox_event_destination UNIQUE (event_id, destination)
);
CREATE INDEX IF NOT EXISTS ix_domain_outbox_ready
    ON domain_outbox (status, available_at);
CREATE INDEX IF NOT EXISTS ix_domain_outbox_lease
    ON domain_outbox (status, lease_until);
