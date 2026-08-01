package postgres

import (
	"strings"
	"testing"
)

func TestAgentProtocolMigrationDropsLegacyStatusConstraintBeforeBackfill(
	t *testing.T,
) {
	t.Parallel()
	content, err := migrationFiles.ReadFile("migrations/003_agent_protocol_v1.sql")
	if err != nil {
		t.Fatalf("read migration: %v", err)
	}
	sql := string(content)
	dropConstraint := strings.Index(
		sql,
		"DROP CONSTRAINT IF EXISTS agent_runs_status_check",
	)
	backfillCancelled := strings.Index(
		sql,
		"SET status = 'cancelled'",
	)
	if dropConstraint < 0 || backfillCancelled < 0 {
		t.Fatal("migration is missing legacy status conversion steps")
	}
	if dropConstraint > backfillCancelled {
		t.Fatal("legacy constraint must be removed before stopped is backfilled")
	}
}

func TestAgentRuntimeMigrationSeparatesRuntimeSchemaAndFencingColumns(
	t *testing.T,
) {
	t.Parallel()
	content, err := migrationFiles.ReadFile(
		"migrations/005_agent_runtime_foundation.sql",
	)
	if err != nil {
		t.Fatalf("read migration: %v", err)
	}
	sql := string(content)
	required := []string{
		"CREATE SCHEMA IF NOT EXISTS agent_runtime",
		"agent_runtime.runtime_executions",
		"agent_runtime.runtime_events",
		"agent_runtime.runtime_artifacts",
		"lease_epoch BIGINT",
		"PRIMARY KEY (execution_id, sequence)",
		"Short-retention Runtime Event Outbox",
	}
	for _, fragment := range required {
		if !strings.Contains(sql, fragment) {
			t.Fatalf("runtime migration is missing %q", fragment)
		}
	}
	if strings.Contains(sql, "CREATE TABLE app_core.runtime_") {
		t.Fatal("Python runtime tables must not be created in app_core")
	}
}

func TestSkillRunProtocolMigrationIsExpandOnlyAndBackfillsLegacyRuns(t *testing.T) {
	t.Parallel()
	content, err := migrationFiles.ReadFile("migrations/006_skill_run_protocol.sql")
	if err != nil {
		t.Fatalf("read migration: %v", err)
	}
	sql := string(content)
	required := []string{
		"model_id TEXT",
		"requested_skill TEXT",
		"resolved_skills JSONB",
		"primary_skill TEXT",
		"selection_source TEXT",
		"skill_snapshot JSONB",
		"model_snapshot JSONB",
		"context_package_id UUID",
		"WHEN 'research_agent' THEN 'research'",
		"WHEN 'fortune_agent' THEN 'fortune'",
	}
	for _, fragment := range required {
		if !strings.Contains(sql, fragment) {
			t.Fatalf("skill protocol migration is missing %q", fragment)
		}
	}
	if strings.Contains(strings.ToUpper(sql), "DROP COLUMN") ||
		strings.Contains(strings.ToUpper(sql), "DROP TABLE") {
		t.Fatal("skill protocol migration must be expand-only")
	}
}

func TestPersonalSpaceMigrationIsExpandOnlyAndPreservesOwnership(t *testing.T) {
	t.Parallel()
	content, err := migrationFiles.ReadFile("migrations/008_personal_space_foundation.sql")
	if err != nil {
		t.Fatalf("read migration: %v", err)
	}
	sql := string(content)
	required := []string{
		"app_core.space_entries",
		"FOREIGN KEY (parent_id, user_id)",
		"app_core.markdown_document_revisions",
		"current_revision_id",
		"app_core.wiki_item_revisions",
		"app_core.wiki_item_sources",
		"app_core.wiki_item_tombstones",
		"folder move would create a cycle",
		"ON DELETE SET NULL (document_revision_id, document_id)",
		"Expand-only migration",
	}
	for _, fragment := range required {
		if !strings.Contains(sql, fragment) {
			t.Fatalf("personal-space migration is missing %q", fragment)
		}
	}
	upper := strings.ToUpper(sql)
	if strings.Contains(upper, "DROP TABLE") || strings.Contains(upper, "DROP COLUMN") {
		t.Fatal("personal-space migration must not remove existing data")
	}
}

func TestWikiProposalMigrationPreservesConfirmationAndAuditBoundaries(t *testing.T) {
	t.Parallel()
	content, err := migrationFiles.ReadFile("migrations/011_wiki_proposal.sql")
	if err != nil {
		t.Fatalf("read migration: %v", err)
	}
	sql := string(content)
	required := []string{
		"app_core.wiki_update_proposals",
		"app_core.wiki_proposal_actions",
		"pending', 'accepted', 'rejected', 'deferred', 'superseded",
		"wiki_update_proposals_resolution_check",
		"resolved_by_user_id = user_id",
		"UNIQUE (user_id, idempotency_key)",
		"ON DELETE SET NULL (target_revision_id, target_item_id)",
		"Expand-only migration",
	}
	for _, fragment := range required {
		if !strings.Contains(sql, fragment) {
			t.Fatalf("proposal migration is missing %q", fragment)
		}
	}
	upper := strings.ToUpper(sql)
	if strings.Contains(upper, "DROP TABLE") || strings.Contains(upper, "DROP COLUMN") {
		t.Fatal("proposal migration must not remove existing data")
	}
}
