ALTER TABLE app_core.agent_runs
    ADD COLUMN IF NOT EXISTS model_id TEXT,
    ADD COLUMN IF NOT EXISTS requested_skill TEXT,
    ADD COLUMN IF NOT EXISTS resolved_skills JSONB,
    ADD COLUMN IF NOT EXISTS primary_skill TEXT,
    ADD COLUMN IF NOT EXISTS selection_source TEXT,
    ADD COLUMN IF NOT EXISTS skill_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS model_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS context_package_id UUID;

UPDATE app_core.agent_runs
SET model_id = COALESCE(NULLIF(model_id, ''), 'auto'),
    requested_skill = COALESCE(
        requested_skill,
        CASE agent_name
            WHEN 'research_agent' THEN 'research'
            WHEN 'fortune_agent' THEN 'fortune'
            ELSE NULL
        END
    ),
    resolved_skills = COALESCE(
        resolved_skills,
        CASE agent_name
            WHEN 'research_agent' THEN '["research"]'::jsonb
            WHEN 'fortune_agent' THEN '["fortune"]'::jsonb
            ELSE '[]'::jsonb
        END
    ),
    primary_skill = COALESCE(
        primary_skill,
        CASE agent_name
            WHEN 'research_agent' THEN 'research'
            WHEN 'fortune_agent' THEN 'fortune'
            ELSE NULL
        END
    ),
    selection_source = COALESCE(selection_source, 'compatibility')
WHERE model_id IS NULL OR resolved_skills IS NULL OR selection_source IS NULL;

ALTER TABLE app_core.agent_runs
    ALTER COLUMN model_id SET DEFAULT 'auto',
    ALTER COLUMN model_id SET NOT NULL;

ALTER TABLE app_core.agent_runs
    ADD CONSTRAINT agent_runs_model_id_check
        CHECK (model_id ~ '^[a-z][a-z0-9_-]{0,63}$'),
    ADD CONSTRAINT agent_runs_requested_skill_check
        CHECK (requested_skill IS NULL OR requested_skill IN ('research', 'fortune')),
    ADD CONSTRAINT agent_runs_resolved_skills_check
        CHECK (
            resolved_skills IS NULL OR (
                jsonb_typeof(resolved_skills) = 'array'
                AND jsonb_array_length(resolved_skills) <= 1
            )
        ),
    ADD CONSTRAINT agent_runs_primary_skill_check
        CHECK (primary_skill IS NULL OR primary_skill IN ('research', 'fortune')),
    ADD CONSTRAINT agent_runs_selection_source_check
        CHECK (
            selection_source IS NULL OR selection_source IN (
                'direct', 'user', 'compatibility', 'automatic', 'fallback'
            )
        );

CREATE INDEX IF NOT EXISTS agent_runs_primary_skill_idx
    ON app_core.agent_runs (primary_skill, started_at DESC)
    WHERE primary_skill IS NOT NULL;
