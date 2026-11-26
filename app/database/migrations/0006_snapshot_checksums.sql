-- Add immutable integrity digests for aggregate snapshots.
-- Existing rows receive an empty sentinel and are rejected by replay until
-- explicitly re-snapshotted; no state is silently trusted without a digest.
CREATE TABLE IF NOT EXISTS aggregate_snapshot_checksums (
    snapshot_id VARCHAR(36) PRIMARY KEY
        REFERENCES aggregate_snapshots(snapshot_id) ON DELETE CASCADE,
    checksum VARCHAR(64) NOT NULL DEFAULT '',
    CONSTRAINT ck_snapshot_checksum_length
        CHECK (checksum = '' OR length(checksum) = 64)
);
