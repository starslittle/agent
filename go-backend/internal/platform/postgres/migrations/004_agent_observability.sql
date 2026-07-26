ALTER TABLE app_core.agent_runs
    ADD COLUMN IF NOT EXISTS trace_id TEXT,
    ADD COLUMN IF NOT EXISTS agent_version TEXT,
    ADD COLUMN IF NOT EXISTS graph_version TEXT,
    ADD COLUMN IF NOT EXISTS prompt_bundle_hash TEXT,
    ADD COLUMN IF NOT EXISTS input_tokens BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS output_tokens BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS cached_tokens BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS total_tokens BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS estimated_cost NUMERIC(18, 8) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS pricing_version TEXT,
    ADD COLUMN IF NOT EXISTS model_call_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS tool_call_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS retrieval_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS total_duration_ms BIGINT;

UPDATE app_core.agent_runs
SET trace_id = execution_id
WHERE trace_id IS NULL;

ALTER TABLE app_core.agent_runs
    ALTER COLUMN trace_id SET NOT NULL;

ALTER TABLE app_core.agent_run_events
    ADD COLUMN IF NOT EXISTS trace_id TEXT,
    ADD COLUMN IF NOT EXISTS span_id TEXT,
    ADD COLUMN IF NOT EXISTS parent_span_id TEXT,
    ADD COLUMN IF NOT EXISTS category TEXT,
    ADD COLUMN IF NOT EXISTS stage TEXT,
    ADD COLUMN IF NOT EXISTS event_schema_version INTEGER NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS content_capture_level TEXT NOT NULL DEFAULT 'hashed'
        CHECK (content_capture_level IN ('off', 'hashed', 'sampled'));

UPDATE app_core.agent_run_events
SET trace_id = execution_id
WHERE trace_id IS NULL;

ALTER TABLE app_core.agent_run_events
    ALTER COLUMN trace_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS agent_run_events_trace_idx
    ON app_core.agent_run_events (trace_id, sequence);

CREATE TABLE IF NOT EXISTS app_core.agent_run_spans (
    id BIGSERIAL PRIMARY KEY,
    run_id UUID NOT NULL
        REFERENCES app_core.agent_runs(id) ON DELETE CASCADE,
    execution_id TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    span_id TEXT NOT NULL,
    parent_span_id TEXT,
    span_type TEXT NOT NULL,
    name TEXT NOT NULL,
    stage TEXT,
    status TEXT NOT NULL
        CHECK (
            status IN (
                'started',
                'completed',
                'failed',
                'cancelled',
                'timed_out'
            )
        ),
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    duration_ms BIGINT,
    input_tokens BIGINT NOT NULL DEFAULT 0,
    output_tokens BIGINT NOT NULL DEFAULT 0,
    cached_tokens BIGINT NOT NULL DEFAULT 0,
    total_tokens BIGINT NOT NULL DEFAULT 0,
    error_code TEXT,
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (execution_id, span_id)
);

CREATE INDEX IF NOT EXISTS agent_run_spans_run_time_idx
    ON app_core.agent_run_spans (run_id, started_at, id);

CREATE TABLE IF NOT EXISTS app_core.prompt_artifacts (
    prompt_hash TEXT PRIMARY KEY,
    relative_path TEXT NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS app_core.agent_run_prompts (
    run_id UUID NOT NULL
        REFERENCES app_core.agent_runs(id) ON DELETE CASCADE,
    sequence BIGINT NOT NULL,
    prompt_hash TEXT NOT NULL
        REFERENCES app_core.prompt_artifacts(prompt_hash),
    stage TEXT NOT NULL,
    rendered_hash TEXT,
    rendered_characters INTEGER,
    iteration INTEGER,
    PRIMARY KEY (run_id, sequence)
);

CREATE INDEX IF NOT EXISTS agent_run_prompts_hash_idx
    ON app_core.agent_run_prompts (prompt_hash, run_id);

CREATE INDEX IF NOT EXISTS agent_runs_observability_list_idx
    ON app_core.agent_runs (started_at DESC, id DESC);
