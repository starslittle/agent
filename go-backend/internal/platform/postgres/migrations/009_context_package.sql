CREATE TABLE IF NOT EXISTS app_core.context_packages (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_core.users(id) ON DELETE CASCADE,
    run_id UUID NOT NULL REFERENCES app_core.agent_runs(id) ON DELETE CASCADE,
    purpose TEXT NOT NULL CHECK (char_length(purpose) BETWEEN 1 AND 80),
    requirements JSONB NOT NULL,
    policy JSONB NOT NULL DEFAULT '{"allow_memory_proposals":false}'::jsonb,
    item_budget INTEGER NOT NULL CHECK (item_budget BETWEEN 0 AND 50),
    character_budget INTEGER NOT NULL CHECK (character_budget BETWEEN 0 AND 50000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (run_id),
    UNIQUE (id, user_id)
);

CREATE TABLE IF NOT EXISTS app_core.context_package_items (
    package_id UUID NOT NULL,
    user_id UUID NOT NULL,
    item_id UUID,
    revision_id UUID,
    item_type TEXT NOT NULL,
    domain TEXT NOT NULL,
    content TEXT NOT NULL,
    source JSONB NOT NULL DEFAULT '{}'::jsonb,
    item_updated_at TIMESTAMPTZ NOT NULL,
    rank INTEGER NOT NULL CHECK (rank > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    redacted_at TIMESTAMPTZ,
    PRIMARY KEY (package_id, rank),
    CONSTRAINT context_package_items_package_fk
        FOREIGN KEY (package_id, user_id)
        REFERENCES app_core.context_packages(id, user_id)
        ON DELETE CASCADE,
    CONSTRAINT context_package_items_revision_fk
        FOREIGN KEY (revision_id, item_id, user_id)
        REFERENCES app_core.wiki_item_revisions(id, item_id, user_id)
        ON DELETE SET NULL (revision_id, item_id)
        DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX IF NOT EXISTS context_package_items_item_idx
    ON app_core.context_package_items (user_id, item_id, created_at DESC)
    WHERE item_id IS NOT NULL;

ALTER TABLE app_core.agent_runs
    DROP CONSTRAINT IF EXISTS agent_runs_context_package_fk;
ALTER TABLE app_core.agent_runs
    ADD CONSTRAINT agent_runs_context_package_fk
    FOREIGN KEY (context_package_id)
    REFERENCES app_core.context_packages(id)
    ON DELETE SET NULL
    DEFERRABLE INITIALLY DEFERRED;

-- Expand-only migration. Disabling Context Package assembly leaves historical
-- frozen packages intact; permanent Wiki deletion redacts their copied content.
