ALTER TABLE app_core.users
    ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'user';

ALTER TABLE app_core.users
    DROP CONSTRAINT IF EXISTS users_role_check;

ALTER TABLE app_core.users
    ADD CONSTRAINT users_role_check
    CHECK (role IN ('user', 'observability_admin'));

CREATE TABLE IF NOT EXISTS app_core.observability_access_audit_logs (
    id BIGSERIAL PRIMARY KEY,
    actor_user_id UUID NOT NULL
        REFERENCES app_core.users(id) ON DELETE RESTRICT,
    action TEXT NOT NULL
        CHECK (action IN ('agent_runs.list', 'agent_runs.detail')),
    target_run_id UUID
        REFERENCES app_core.agent_runs(id) ON DELETE SET NULL,
    filters JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS observability_access_audit_actor_time_idx
    ON app_core.observability_access_audit_logs (actor_user_id, created_at DESC);

