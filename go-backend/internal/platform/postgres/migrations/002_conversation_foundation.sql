CREATE TABLE IF NOT EXISTS app_core.conversations (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_core.users(id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT '新的对话',
    agent_name TEXT NOT NULL DEFAULT 'default_llm_agent',
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'archived', 'deleted')),
    last_message_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS conversations_user_activity_idx
    ON app_core.conversations (
        user_id,
        COALESCE(last_message_at, created_at) DESC,
        id DESC
    )
    WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS app_core.messages (
    id UUID PRIMARY KEY,
    conversation_id UUID NOT NULL
        REFERENCES app_core.conversations(id) ON DELETE CASCADE,
    client_message_id UUID,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL
        CHECK (status IN ('pending', 'streaming', 'completed', 'stopped', 'failed')),
    sequence_id BIGSERIAL NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    UNIQUE (conversation_id, client_message_id),
    UNIQUE (conversation_id, sequence_id)
);

CREATE INDEX IF NOT EXISTS messages_conversation_sequence_idx
    ON app_core.messages (conversation_id, sequence_id DESC);

CREATE TABLE IF NOT EXISTS app_core.agent_runs (
    id UUID PRIMARY KEY,
    conversation_id UUID NOT NULL
        REFERENCES app_core.conversations(id) ON DELETE CASCADE,
    user_message_id UUID NOT NULL
        REFERENCES app_core.messages(id) ON DELETE CASCADE,
    assistant_message_id UUID NOT NULL
        REFERENCES app_core.messages(id) ON DELETE CASCADE,
    request_id TEXT NOT NULL UNIQUE,
    agent_name TEXT NOT NULL,
    model_name TEXT,
    status TEXT NOT NULL
        CHECK (status IN ('queued', 'running', 'completed', 'stopped', 'failed')),
    error_code TEXT,
    error_detail TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    first_token_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE UNIQUE INDEX IF NOT EXISTS agent_runs_one_active_per_conversation_idx
    ON app_core.agent_runs (conversation_id)
    WHERE status IN ('queued', 'running');

CREATE INDEX IF NOT EXISTS agent_runs_conversation_started_idx
    ON app_core.agent_runs (conversation_id, started_at DESC);
