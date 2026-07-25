CREATE SCHEMA IF NOT EXISTS app_core;

CREATE TABLE IF NOT EXISTS app_core.users (
    id UUID PRIMARY KEY,
    email TEXT NOT NULL,
    display_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'disabled', 'deleted')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS users_email_normalized_idx
    ON app_core.users (LOWER(email));

CREATE TABLE IF NOT EXISTS app_core.auth_identities (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_core.users(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    provider_subject TEXT NOT NULL,
    email TEXT,
    email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (provider, provider_subject)
);

CREATE TABLE IF NOT EXISTS app_core.password_credentials (
    user_id UUID PRIMARY KEY REFERENCES app_core.users(id) ON DELETE CASCADE,
    password_hash TEXT NOT NULL,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS app_core.sessions (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_core.users(id) ON DELETE CASCADE,
    token_hash BYTEA NOT NULL UNIQUE,
    csrf_token TEXT NOT NULL,
    user_agent TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS sessions_user_id_idx
    ON app_core.sessions (user_id);
CREATE INDEX IF NOT EXISTS sessions_expires_at_idx
    ON app_core.sessions (expires_at)
    WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS app_core.login_audit_logs (
    id BIGSERIAL PRIMARY KEY,
    email TEXT NOT NULL,
    user_id UUID REFERENCES app_core.users(id) ON DELETE SET NULL,
    success BOOLEAN NOT NULL,
    ip_address TEXT NOT NULL DEFAULT '',
    user_agent TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS login_audit_created_at_idx
    ON app_core.login_audit_logs (created_at DESC);
