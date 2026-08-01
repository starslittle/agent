CREATE TABLE IF NOT EXISTS app_core.space_entries (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_core.users(id) ON DELETE CASCADE,
    parent_id UUID,
    kind TEXT NOT NULL CHECK (kind IN ('folder', 'document')),
    name TEXT NOT NULL CHECK (char_length(name) BETWEEN 1 AND 120),
    name_key TEXT NOT NULL CHECK (char_length(name_key) BETWEEN 1 AND 240),
    version BIGINT NOT NULL DEFAULT 1 CHECK (version > 0),
    last_opened_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id, user_id),
    CONSTRAINT space_entries_document_parent_check
        CHECK (kind = 'folder' OR parent_id IS NOT NULL),
    CONSTRAINT space_entries_parent_user_fk
        FOREIGN KEY (parent_id, user_id)
        REFERENCES app_core.space_entries(id, user_id)
        ON DELETE RESTRICT
        DEFERRABLE INITIALLY IMMEDIATE
);

CREATE UNIQUE INDEX IF NOT EXISTS space_entries_sibling_name_idx
    ON app_core.space_entries (
        user_id,
        COALESCE(parent_id, '00000000-0000-0000-0000-000000000000'::uuid),
        name_key
    );

CREATE INDEX IF NOT EXISTS space_entries_parent_sort_idx
    ON app_core.space_entries (user_id, parent_id, kind, name_key, id);

CREATE INDEX IF NOT EXISTS space_entries_recent_idx
    ON app_core.space_entries (
        user_id,
        parent_id,
        COALESCE(last_opened_at, updated_at) DESC,
        id DESC
    );

CREATE OR REPLACE FUNCTION app_core.validate_space_entry_parent()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    parent_kind TEXT;
    cycle_exists BOOLEAN;
BEGIN
    IF NEW.parent_id IS NULL THEN
        IF NEW.kind = 'document' THEN
            RAISE EXCEPTION 'documents require a parent folder' USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;

    SELECT kind INTO parent_kind
    FROM app_core.space_entries
    WHERE id = NEW.parent_id AND user_id = NEW.user_id;

    IF parent_kind IS NULL OR parent_kind <> 'folder' THEN
        RAISE EXCEPTION 'space parent must be a folder owned by the same user'
            USING ERRCODE = '23514';
    END IF;

    IF NEW.kind = 'folder' THEN
        IF NEW.parent_id = NEW.id THEN
            RAISE EXCEPTION 'folder cannot parent itself' USING ERRCODE = '23514';
        END IF;
        WITH RECURSIVE descendants AS (
            SELECT id
            FROM app_core.space_entries
            WHERE parent_id = NEW.id AND user_id = NEW.user_id
            UNION ALL
            SELECT child.id
            FROM app_core.space_entries child
            JOIN descendants d ON child.parent_id = d.id
            WHERE child.user_id = NEW.user_id
        )
        SELECT EXISTS (
            SELECT 1 FROM descendants WHERE id = NEW.parent_id
        ) INTO cycle_exists;
        IF cycle_exists THEN
            RAISE EXCEPTION 'folder move would create a cycle' USING ERRCODE = '23514';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS space_entries_validate_parent
    ON app_core.space_entries;
CREATE TRIGGER space_entries_validate_parent
BEFORE INSERT OR UPDATE OF parent_id, user_id, kind
ON app_core.space_entries
FOR EACH ROW EXECUTE FUNCTION app_core.validate_space_entry_parent();

CREATE TABLE IF NOT EXISTS app_core.markdown_documents (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    current_revision_id UUID,
    extraction_status TEXT NOT NULL DEFAULT 'not_requested'
        CHECK (extraction_status IN ('not_requested', 'queued', 'running', 'completed', 'failed')),
    deleted_at TIMESTAMPTZ,
    UNIQUE (id, user_id),
    CONSTRAINT markdown_documents_entry_fk
        FOREIGN KEY (id, user_id)
        REFERENCES app_core.space_entries(id, user_id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS app_core.markdown_document_revisions (
    id UUID PRIMARY KEY,
    document_id UUID NOT NULL,
    user_id UUID NOT NULL,
    revision_number BIGINT NOT NULL CHECK (revision_number > 0),
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL CHECK (char_length(content_hash) = 64),
    size_bytes BIGINT NOT NULL CHECK (size_bytes >= 0),
    source TEXT NOT NULL CHECK (source IN ('manual', 'import')),
    original_relative_path TEXT,
    media_type TEXT NOT NULL DEFAULT 'text/markdown'
        CHECK (media_type = 'text/markdown'),
    created_by TEXT NOT NULL CHECK (created_by IN ('user', 'system', 'agent')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_id, revision_number),
    UNIQUE (id, document_id, user_id),
    CONSTRAINT markdown_document_revisions_document_fk
        FOREIGN KEY (document_id, user_id)
        REFERENCES app_core.markdown_documents(id, user_id)
        ON DELETE CASCADE
);

ALTER TABLE app_core.markdown_documents
    DROP CONSTRAINT IF EXISTS markdown_documents_current_revision_fk;
ALTER TABLE app_core.markdown_documents
    ADD CONSTRAINT markdown_documents_current_revision_fk
    FOREIGN KEY (current_revision_id, id, user_id)
    REFERENCES app_core.markdown_document_revisions(id, document_id, user_id)
    ON DELETE NO ACTION
    DEFERRABLE INITIALLY DEFERRED;

CREATE INDEX IF NOT EXISTS markdown_document_revisions_document_idx
    ON app_core.markdown_document_revisions (user_id, document_id, revision_number DESC);

CREATE TABLE IF NOT EXISTS app_core.wiki_items (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_core.users(id) ON DELETE CASCADE,
    item_type TEXT NOT NULL
        CHECK (item_type IN ('confirmed_fact', 'current_state', 'personal_rule', 'ai_analysis')),
    domain TEXT NOT NULL CHECK (char_length(domain) BETWEEN 1 AND 80),
    status TEXT NOT NULL
        CHECK (status IN ('candidate', 'confirmed', 'rejected', 'outdated', 'forgotten')),
    status_before_forgotten TEXT
        CHECK (status_before_forgotten IN ('candidate', 'confirmed', 'rejected', 'outdated')),
    current_revision_id UUID,
    confirmed_by_user BOOLEAN NOT NULL DEFAULT FALSE,
    effective_at TIMESTAMPTZ,
    version BIGINT NOT NULL DEFAULT 1 CHECK (version > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id, user_id),
    CONSTRAINT wiki_items_confirmation_check
        CHECK (status <> 'confirmed' OR confirmed_by_user)
);

CREATE TABLE IF NOT EXISTS app_core.wiki_item_revisions (
    id UUID PRIMARY KEY,
    item_id UUID NOT NULL,
    user_id UUID NOT NULL,
    revision_number BIGINT NOT NULL CHECK (revision_number > 0),
    content TEXT NOT NULL CHECK (char_length(content) BETWEEN 1 AND 20000),
    created_by TEXT NOT NULL CHECK (created_by IN ('user', 'system', 'agent')),
    replaces_revision_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (item_id, revision_number),
    UNIQUE (id, item_id, user_id),
    CONSTRAINT wiki_item_revisions_item_fk
        FOREIGN KEY (item_id, user_id)
        REFERENCES app_core.wiki_items(id, user_id)
        ON DELETE CASCADE,
    CONSTRAINT wiki_item_revisions_replaces_fk
        FOREIGN KEY (replaces_revision_id, item_id, user_id)
        REFERENCES app_core.wiki_item_revisions(id, item_id, user_id)
        ON DELETE NO ACTION
        DEFERRABLE INITIALLY DEFERRED
);

ALTER TABLE app_core.wiki_items
    DROP CONSTRAINT IF EXISTS wiki_items_current_revision_fk;
ALTER TABLE app_core.wiki_items
    ADD CONSTRAINT wiki_items_current_revision_fk
    FOREIGN KEY (current_revision_id, id, user_id)
    REFERENCES app_core.wiki_item_revisions(id, item_id, user_id)
    ON DELETE NO ACTION
    DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE IF NOT EXISTS app_core.wiki_item_sources (
    id UUID PRIMARY KEY,
    item_id UUID NOT NULL,
    revision_id UUID NOT NULL,
    user_id UUID NOT NULL,
    source_type TEXT NOT NULL
        CHECK (source_type IN (
            'user_stated', 'user_confirmed', 'ai_inferred', 'document_extracted',
            'tool_derived', 'fortune_narrative', 'review_derived'
        )),
    source_ref TEXT,
    source_detail TEXT,
    document_id UUID,
    document_revision_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT wiki_item_sources_revision_fk
        FOREIGN KEY (revision_id, item_id, user_id)
        REFERENCES app_core.wiki_item_revisions(id, item_id, user_id)
        ON DELETE CASCADE,
    CONSTRAINT wiki_item_sources_document_revision_fk
        FOREIGN KEY (document_revision_id, document_id, user_id)
        REFERENCES app_core.markdown_document_revisions(id, document_id, user_id)
        ON DELETE SET NULL (document_revision_id, document_id)
        DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT wiki_item_sources_document_pair_check
        CHECK ((document_id IS NULL) = (document_revision_id IS NULL))
);

CREATE INDEX IF NOT EXISTS wiki_items_user_status_idx
    ON app_core.wiki_items (user_id, status, updated_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS wiki_item_revisions_item_idx
    ON app_core.wiki_item_revisions (user_id, item_id, revision_number DESC);
CREATE INDEX IF NOT EXISTS wiki_item_sources_document_idx
    ON app_core.wiki_item_sources (user_id, document_id, document_revision_id)
    WHERE document_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS app_core.wiki_item_tombstones (
    item_id UUID NOT NULL,
    user_id UUID NOT NULL REFERENCES app_core.users(id) ON DELETE CASCADE,
    deleted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_by_user UUID NOT NULL REFERENCES app_core.users(id) ON DELETE RESTRICT,
    PRIMARY KEY (item_id, user_id),
    CHECK (user_id = deleted_by_user)
);

-- Expand-only migration. Routine rollback disables ROUND-03 behavior and keeps
-- Folder, Document, Revision, Source and tombstone history intact.
