package postgres

import (
	"context"
	"os"
	"testing"
	"time"

	"github.com/starslittle/agent/go-backend/internal/auth"
	"github.com/starslittle/agent/go-backend/internal/conversation"
)

func TestObservabilityAccessMigrationQueriesAndAuditIntegration(t *testing.T) {
	databaseURL := os.Getenv("TEST_DATABASE_URL")
	if databaseURL == "" {
		t.Skip("TEST_DATABASE_URL is not configured")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	store, err := Open(ctx, databaseURL)
	if err != nil {
		t.Fatalf("Open() error = %v", err)
	}
	defer store.Close()
	if err := store.Migrate(ctx); err != nil {
		t.Fatalf("Migrate() error = %v", err)
	}

	adminID := "70000000-0000-4000-8000-000000000001"
	ownerID := "70000000-0000-4000-8000-000000000002"
	conversationID := "70000000-0000-4000-8000-000000000003"
	userMessageID := "70000000-0000-4000-8000-000000000004"
	assistantMessageID := "70000000-0000-4000-8000-000000000005"
	runID := "70000000-0000-4000-8000-000000000006"
	defer func() {
		cleanupCtx, cleanupCancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cleanupCancel()
		_, _ = store.pool.Exec(cleanupCtx, "DELETE FROM app_core.observability_access_audit_logs WHERE actor_user_id=$1", adminID)
		_, _ = store.pool.Exec(cleanupCtx, "DELETE FROM app_core.users WHERE id = ANY($1::uuid[])", []string{adminID, ownerID})
	}()

	for _, user := range []auth.CreateUserParams{
		{ID: adminID, Email: "task028-admin@example.com", DisplayName: "Observer", PasswordHash: "hash"},
		{ID: ownerID, Email: "task028-owner@example.com", DisplayName: "Owner", PasswordHash: "hash"},
	} {
		if _, err := store.CreateUser(ctx, user); err != nil {
			t.Fatalf("CreateUser(%s) error = %v", user.ID, err)
		}
	}
	if _, err := store.pool.Exec(ctx, "UPDATE app_core.users SET role=$2 WHERE id=$1", adminID, auth.RoleObservabilityAdmin); err != nil {
		t.Fatalf("grant role: %v", err)
	}
	startedAt := time.Date(2026, 8, 1, 8, 0, 0, 0, time.UTC)
	if _, err := store.pool.Exec(ctx, `
		INSERT INTO app_core.conversations (id, user_id, title) VALUES ($1, $2, 'Task 028')
	`, conversationID, ownerID); err != nil {
		t.Fatalf("insert conversation: %v", err)
	}
	if _, err := store.pool.Exec(ctx, `
		INSERT INTO app_core.messages (id, conversation_id, role, content, status)
		VALUES ($1, $3, 'user', 'private user body', 'completed'),
		       ($2, $3, 'assistant', 'private assistant body', 'completed')
	`, userMessageID, assistantMessageID, conversationID); err != nil {
		t.Fatalf("insert messages: %v", err)
	}
	if _, err := store.pool.Exec(ctx, `
		INSERT INTO app_core.agent_runs (
			id, conversation_id, user_message_id, assistant_message_id,
			request_id, execution_id, idempotency_key, trace_id,
			agent_name, model_id, model_name, requested_skill,
			resolved_skills, primary_skill, selection_source, actual_route,
			status, error_code, error_detail, protocol_version, started_at, completed_at
		) VALUES (
			$1, $2, $3, $4, 'task028-request', 'task028-execution',
			'task028-idempotency', 'task028-trace', 'default_llm_agent',
			'auto', 'qwen-test', 'research', '["research"]'::jsonb,
			'research', 'user', 'research_graph', 'failed', 'tool_failed',
			'private error detail', 1, $5, $5
		)
	`, runID, conversationID, userMessageID, assistantMessageID, startedAt); err != nil {
		t.Fatalf("insert run: %v", err)
	}

	items, err := store.ListObservableAgentRuns(ctx, conversation.ObservabilityRunListParams{
		UserID: ownerID, Skill: "research", Workflow: "research_graph",
		Model: "qwen-test", Status: "failed", ErrorCode: "tool_failed",
		From: timePointer(startedAt.Add(-time.Minute)), To: timePointer(startedAt.Add(time.Minute)), Limit: 20,
	})
	if err != nil {
		t.Fatalf("ListObservableAgentRuns() error = %v", err)
	}
	if len(items) != 1 || items[0].ID != runID || items[0].OwnerUserID != ownerID {
		t.Fatalf("items = %#v", items)
	}

	detail, err := store.FindObservableAgentRunDetail(ctx, runID)
	if err != nil {
		t.Fatalf("FindObservableAgentRunDetail() error = %v", err)
	}
	if detail.Run.OwnerUserID != ownerID || detail.Run.ConversationID != conversationID {
		t.Fatalf("detail owner projection = %#v", detail.Run)
	}
	if err := store.RecordObservabilityAccess(ctx, auth.ObservabilityAccessAudit{
		ActorUserID: adminID,
		Action:      "agent_runs.detail",
		TargetRunID: runID,
		Filters:     map[string]string{},
		CreatedAt:   time.Now().UTC(),
	}); err != nil {
		t.Fatalf("RecordObservabilityAccess() error = %v", err)
	}
	var auditCount int
	if err := store.pool.QueryRow(ctx, `
		SELECT COUNT(*) FROM app_core.observability_access_audit_logs
		WHERE actor_user_id=$1 AND target_run_id=$2 AND action='agent_runs.detail'
	`, adminID, runID).Scan(&auditCount); err != nil {
		t.Fatalf("query audit: %v", err)
	}
	if auditCount != 1 {
		t.Fatalf("audit count = %d, want 1", auditCount)
	}
}

func timePointer(value time.Time) *time.Time { return &value }
