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
