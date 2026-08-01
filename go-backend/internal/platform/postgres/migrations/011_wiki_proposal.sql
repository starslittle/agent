CREATE TABLE IF NOT EXISTS app_core.wiki_update_proposals (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_core.users(id) ON DELETE CASCADE,
    target_item_id UUID,
    target_revision_id UUID,
    operation TEXT NOT NULL,
    item_type TEXT NOT NULL
        CHECK (item_type IN ('confirmed_fact', 'current_state', 'personal_rule', 'ai_analysis')),
    domain TEXT NOT NULL CHECK (char_length(domain) BETWEEN 1 AND 80),
    proposed_content TEXT NOT NULL CHECK (char_length(proposed_content) BETWEEN 1 AND 20000),
    source_type TEXT NOT NULL
        CHECK (source_type IN (
            'user_stated', 'user_confirmed', 'ai_inferred', 'document_extracted',
            'tool_derived', 'fortune_narrative', 'review_derived'
        )),
    source_ref TEXT CHECK (source_ref IS NULL OR char_length(source_ref) <= 2000),
    source_detail TEXT CHECK (source_detail IS NULL OR char_length(source_detail) <= 8000),
    document_id UUID,
    document_revision_id UUID,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'accepted', 'rejected', 'deferred', 'superseded')),
    final_content TEXT CHECK (final_content IS NULL OR char_length(final_content) BETWEEN 1 AND 20000),
    resolution_action TEXT CHECK (resolution_action IN ('accept', 'reject', 'defer')),
    resolved_by_user_id UUID REFERENCES app_core.users(id) ON DELETE RESTRICT,
    resolved_at TIMESTAMPTZ,
    applied_item_id UUID,
    applied_revision_id UUID,
    created_by TEXT NOT NULL CHECK (created_by IN ('agent', 'system')),
    version BIGINT NOT NULL DEFAULT 1 CHECK (version > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id, user_id),
    CONSTRAINT wiki_update_proposals_target_pair_check
        CHECK ((target_item_id IS NULL) = (target_revision_id IS NULL)),
    CONSTRAINT wiki_update_proposals_operation_check
        CHECK (operation IN ('create', 'update')
            AND (operation = 'update' OR (target_item_id IS NULL AND target_revision_id IS NULL))),
    CONSTRAINT wiki_update_proposals_document_pair_check
        CHECK ((document_id IS NULL) = (document_revision_id IS NULL)),
    CONSTRAINT wiki_update_proposals_resolver_check
        CHECK (resolved_by_user_id IS NULL OR resolved_by_user_id = user_id),
    CONSTRAINT wiki_update_proposals_applied_pair_check
        CHECK ((applied_item_id IS NULL) = (applied_revision_id IS NULL)),
    CONSTRAINT wiki_update_proposals_target_revision_fk
        FOREIGN KEY (target_revision_id, target_item_id, user_id)
        REFERENCES app_core.wiki_item_revisions(id, item_id, user_id)
        ON DELETE SET NULL (target_revision_id, target_item_id),
    CONSTRAINT wiki_update_proposals_document_revision_fk
        FOREIGN KEY (document_revision_id, document_id, user_id)
        REFERENCES app_core.markdown_document_revisions(id, document_id, user_id)
        ON DELETE SET NULL (document_revision_id, document_id)
        DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT wiki_update_proposals_resolution_check CHECK (
        (status IN ('pending', 'superseded') AND resolution_action IS NULL AND final_content IS NULL
            AND resolved_by_user_id IS NULL AND resolved_at IS NULL AND applied_item_id IS NULL)
        OR (status = 'deferred' AND resolution_action = 'defer' AND resolved_by_user_id IS NOT NULL
            AND resolved_at IS NOT NULL AND final_content IS NULL AND applied_item_id IS NULL)
        OR (status = 'rejected' AND resolution_action = 'reject' AND resolved_by_user_id IS NOT NULL
            AND resolved_at IS NOT NULL AND final_content IS NULL AND applied_item_id IS NULL)
        OR (status = 'accepted' AND resolution_action = 'accept' AND resolved_by_user_id IS NOT NULL AND resolved_at IS NOT NULL
            AND final_content IS NOT NULL AND applied_item_id IS NOT NULL AND applied_revision_id IS NOT NULL)
    )
);

CREATE TABLE IF NOT EXISTS app_core.wiki_proposal_actions (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_core.users(id) ON DELETE CASCADE,
    proposal_id UUID NOT NULL,
    idempotency_key TEXT NOT NULL CHECK (char_length(idempotency_key) BETWEEN 1 AND 200),
    action TEXT NOT NULL CHECK (action IN ('accept', 'reject', 'defer')),
    request_hash TEXT NOT NULL CHECK (char_length(request_hash) = 64),
    result JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, idempotency_key),
    CONSTRAINT wiki_proposal_actions_proposal_fk
        FOREIGN KEY (proposal_id, user_id)
        REFERENCES app_core.wiki_update_proposals(id, user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS wiki_update_proposals_user_status_idx
    ON app_core.wiki_update_proposals (user_id, status, updated_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS wiki_update_proposals_document_idx
    ON app_core.wiki_update_proposals (user_id, document_id, document_revision_id)
    WHERE document_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS wiki_update_proposals_target_idx
    ON app_core.wiki_update_proposals (user_id, target_item_id, target_revision_id)
    WHERE target_item_id IS NOT NULL;

-- Expand-only migration. Disabling proposal generation or confirmation keeps
-- pending decisions, accepted Wiki revisions and user audit history intact.
