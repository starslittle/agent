CREATE SCHEMA IF NOT EXISTS agent_runtime;

CREATE TABLE IF NOT EXISTS agent_runtime.runtime_executions (
    execution_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash CHAR(64) NOT NULL
        CHECK (request_hash ~ '^[0-9a-f]{64}$'),
    protocol_version INTEGER NOT NULL DEFAULT 1
        CHECK (protocol_version > 0),
    status TEXT NOT NULL
        CHECK (
            status IN (
                'queued',
                'running',
                'cancel_requested',
                'completed',
                'cancelled',
                'failed',
                'timed_out'
            )
        ),
    owner_id TEXT,
    lease_epoch BIGINT NOT NULL DEFAULT 0
        CHECK (lease_epoch >= 0),
    lease_expires_at TIMESTAMPTZ,
    last_sequence BIGINT NOT NULL DEFAULT 0
        CHECK (last_sequence >= 0),
    deadline_at TIMESTAMPTZ NOT NULL,
    agent_name TEXT NOT NULL,
    workflow_name TEXT,
    graph_version TEXT NOT NULL,
    service_version TEXT NOT NULL,
    shadow BOOLEAN NOT NULL DEFAULT FALSE,
    error JSONB,
    provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT runtime_executions_lease_shape_check
        CHECK (
            (owner_id IS NULL AND lease_expires_at IS NULL)
            OR
            (owner_id IS NOT NULL AND lease_epoch > 0
                AND lease_expires_at IS NOT NULL)
        ),
    UNIQUE (run_id),
    UNIQUE (idempotency_key)
);

CREATE INDEX IF NOT EXISTS runtime_executions_active_lease_idx
    ON agent_runtime.runtime_executions (lease_expires_at, execution_id)
    WHERE status IN ('queued', 'running', 'cancel_requested');

CREATE INDEX IF NOT EXISTS runtime_executions_retention_idx
    ON agent_runtime.runtime_executions (expires_at, execution_id);

CREATE TABLE IF NOT EXISTS agent_runtime.runtime_events (
    execution_id TEXT NOT NULL
        REFERENCES agent_runtime.runtime_executions(execution_id)
        ON DELETE CASCADE,
    sequence BIGINT NOT NULL CHECK (sequence > 0),
    lease_epoch BIGINT NOT NULL CHECK (lease_epoch > 0),
    run_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    trace_id TEXT NOT NULL,
    span_id TEXT,
    parent_span_id TEXT,
    category TEXT NOT NULL,
    stage TEXT,
    event_schema_version INTEGER NOT NULL DEFAULT 1
        CHECK (event_schema_version > 0),
    content_capture_level TEXT NOT NULL DEFAULT 'hashed'
        CHECK (content_capture_level IN ('off', 'hashed', 'sampled')),
    data JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (execution_id, sequence)
);

CREATE INDEX IF NOT EXISTS runtime_events_created_idx
    ON agent_runtime.runtime_events (created_at, execution_id, sequence);

CREATE INDEX IF NOT EXISTS runtime_events_trace_idx
    ON agent_runtime.runtime_events (trace_id, sequence);

CREATE TABLE IF NOT EXISTS agent_runtime.runtime_artifacts (
    execution_id TEXT NOT NULL
        REFERENCES agent_runtime.runtime_executions(execution_id)
        ON DELETE CASCADE,
    artifact_id TEXT NOT NULL,
    lease_epoch BIGINT NOT NULL CHECK (lease_epoch > 0),
    artifact_type TEXT NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1
        CHECK (schema_version > 0),
    content_hash CHAR(64) NOT NULL
        CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    media_type TEXT NOT NULL,
    size_bytes BIGINT NOT NULL CHECK (size_bytes >= 0),
    storage_kind TEXT NOT NULL
        CHECK (storage_kind IN ('inline', 'object')),
    inline_content BYTEA,
    object_uri TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (execution_id, artifact_id),
    CONSTRAINT runtime_artifacts_storage_shape_check
        CHECK (
            (storage_kind = 'inline'
                AND inline_content IS NOT NULL
                AND object_uri IS NULL)
            OR
            (storage_kind = 'object'
                AND inline_content IS NULL
                AND object_uri IS NOT NULL)
        )
);

CREATE INDEX IF NOT EXISTS runtime_artifacts_retention_idx
    ON agent_runtime.runtime_artifacts (expires_at, execution_id);

COMMENT ON SCHEMA agent_runtime IS
    'Python Agent Runtime coordination state; not product business history.';

COMMENT ON TABLE agent_runtime.runtime_events IS
    'Short-retention Runtime Event Outbox for cross-process starting_after replay.';
