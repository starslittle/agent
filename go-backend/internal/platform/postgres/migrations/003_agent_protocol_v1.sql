DROP INDEX IF EXISTS app_core.agent_runs_one_active_per_conversation_idx;

ALTER TABLE app_core.agent_runs
    DROP CONSTRAINT IF EXISTS agent_runs_status_check;

UPDATE app_core.agent_runs
SET status = 'cancelled'
WHERE status = 'stopped';

ALTER TABLE app_core.agent_runs
    ADD CONSTRAINT agent_runs_status_check
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
    );

ALTER TABLE app_core.agent_runs
    ADD COLUMN IF NOT EXISTS execution_id TEXT,
    ADD COLUMN IF NOT EXISTS idempotency_key TEXT,
    ADD COLUMN IF NOT EXISTS protocol_version INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS service_version TEXT,
    ADD COLUMN IF NOT EXISTS actual_route TEXT,
    ADD COLUMN IF NOT EXISTS last_sequence BIGINT NOT NULL DEFAULT 0;

UPDATE app_core.agent_runs
SET execution_id = COALESCE(execution_id, id::text),
    idempotency_key = COALESCE(idempotency_key, id::text)
WHERE execution_id IS NULL OR idempotency_key IS NULL;

ALTER TABLE app_core.agent_runs
    ALTER COLUMN execution_id SET NOT NULL,
    ALTER COLUMN idempotency_key SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS agent_runs_execution_id_idx
    ON app_core.agent_runs (execution_id);

CREATE UNIQUE INDEX IF NOT EXISTS agent_runs_idempotency_key_idx
    ON app_core.agent_runs (idempotency_key);

CREATE UNIQUE INDEX agent_runs_one_active_per_conversation_idx
    ON app_core.agent_runs (conversation_id)
    WHERE status IN ('queued', 'running', 'cancel_requested');

CREATE TABLE IF NOT EXISTS app_core.agent_run_events (
    id BIGSERIAL PRIMARY KEY,
    run_id UUID NOT NULL
        REFERENCES app_core.agent_runs(id) ON DELETE CASCADE,
    execution_id TEXT NOT NULL,
    sequence BIGINT NOT NULL CHECK (sequence > 0),
    event_type TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    data JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (execution_id, sequence)
);

CREATE INDEX IF NOT EXISTS agent_run_events_run_sequence_idx
    ON app_core.agent_run_events (run_id, sequence);
