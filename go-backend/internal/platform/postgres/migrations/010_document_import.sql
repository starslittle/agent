CREATE TABLE IF NOT EXISTS app_core.document_import_batches (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_core.users(id) ON DELETE CASCADE,
    idempotency_key TEXT NOT NULL CHECK (char_length(idempotency_key) BETWEEN 1 AND 200),
    target_folder_id UUID,
    root_name TEXT,
    manifest_hash TEXT NOT NULL CHECK (char_length(manifest_hash) = 64),
    status TEXT NOT NULL CHECK (status IN ('completed', 'failed')),
    result JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, idempotency_key),
    CONSTRAINT document_import_batches_target_fk
        FOREIGN KEY (target_folder_id, user_id)
        REFERENCES app_core.space_entries(id, user_id)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS document_import_batches_user_created_idx
    ON app_core.document_import_batches (user_id, created_at DESC);

-- Expand-only migration. Imported Documents remain ordinary versioned Space
-- entries if the import feature is later disabled.
