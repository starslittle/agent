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
