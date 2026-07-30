package postgres

import (
	"context"
	"errors"
	"os"
	"testing"
	"time"

	"github.com/starslittle/agent/go-backend/internal/agent"
	"github.com/starslittle/agent/go-backend/internal/auth"
	"github.com/starslittle/agent/go-backend/internal/conversation"
)

func TestRunCreateIdempotencyAndSupervisorClaimIntegration(t *testing.T) {
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

	userID := auth.NewID()
	if _, err := store.CreateUser(ctx, auth.CreateUserParams{
		ID:           userID,
		Email:        userID + "@example.com",
		DisplayName:  "run-supervisor-test",
		PasswordHash: "integration-test-hash",
	}); err != nil {
		t.Fatalf("CreateUser() error = %v", err)
	}
	t.Cleanup(func() {
		cleanupCtx, cleanupCancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cleanupCancel()
		_, _ = store.pool.Exec(
			cleanupCtx,
			"DELETE FROM app_core.users WHERE id=$1",
			userID,
		)
	})

	service := conversation.NewService(store)
	item, err := service.Create(ctx, userID, conversation.DefaultAgent)
	if err != nil {
		t.Fatalf("Create() error = %v", err)
	}
	clientMessageID := auth.NewID()
	idempotencyKey := "create-run-" + clientMessageID
	params := conversation.StartGenerationParams{
		UserID:          userID,
		ConversationID:  item.ID,
		ClientMessageID: clientMessageID,
		IdempotencyKey:  idempotencyKey,
		RequestID:       auth.NewID(),
		Content:         "创建一个可恢复的 Run",
		AgentName:       conversation.DefaultAgent,
	}
	first, err := service.CreateRun(ctx, params)
	if err != nil {
		t.Fatalf("first CreateRun() error = %v", err)
	}
	params.RequestID = auth.NewID()
	second, err := service.CreateRun(ctx, params)
	if err != nil {
		t.Fatalf("replayed CreateRun() error = %v", err)
	}
	if !second.Replayed ||
		first.Run.ID != second.Run.ID ||
		first.Run.ExecutionID != second.Run.ExecutionID ||
		first.UserMessage.ID != second.UserMessage.ID ||
		first.Assistant.ID != second.Assistant.ID {
		t.Fatalf("idempotent identities differ: first=%#v second=%#v", first, second)
	}

	var runCount, messageCount int
	if err := store.pool.QueryRow(ctx, `
		SELECT
			(SELECT COUNT(*) FROM app_core.agent_runs WHERE conversation_id=$1),
			(SELECT COUNT(*) FROM app_core.messages WHERE conversation_id=$1)
	`, item.ID).Scan(&runCount, &messageCount); err != nil {
		t.Fatalf("count created records: %v", err)
	}
	if runCount != 1 || messageCount != 2 {
		t.Fatalf("created runs/messages = %d/%d, want 1/2", runCount, messageCount)
	}

	conflicting := params
	conflicting.Content = "不同请求内容"
	if _, err := service.CreateRun(
		ctx,
		conflicting,
	); !errors.Is(err, conversation.ErrIdempotencyConflict) {
		t.Fatalf("conflicting CreateRun() error = %v", err)
	}

	firstClaim, ok, err := service.ClaimRun(
		ctx,
		first.Run.ID,
		"owner-a",
		time.Now().UTC().Add(time.Minute),
	)
	if err != nil || !ok {
		t.Fatalf("first ClaimRun() ok=%v error=%v", ok, err)
	}
	if firstClaim.PreviousStatus != string(agent.StatusQueued) ||
		firstClaim.Lease.Epoch != 1 {
		t.Fatalf("unexpected first claim: %#v", firstClaim)
	}
	if _, ok, err := service.ClaimRun(
		ctx,
		first.Run.ID,
		"owner-b",
		time.Now().UTC().Add(time.Minute),
	); err != nil || ok {
		t.Fatalf("duplicate ClaimRun() ok=%v error=%v", ok, err)
	}
	if err := service.ReleaseRunLease(
		ctx,
		first.Run.ID,
		firstClaim.Lease,
	); err != nil {
		t.Fatalf("ReleaseRunLease() error = %v", err)
	}

	secondClaim, ok, err := service.ClaimRun(
		ctx,
		first.Run.ID,
		"owner-b",
		time.Now().UTC().Add(time.Minute),
	)
	if err != nil || !ok {
		t.Fatalf("takeover ClaimRun() ok=%v error=%v", ok, err)
	}
	if secondClaim.PreviousStatus != string(agent.StatusRunning) ||
		secondClaim.Lease.Epoch != 2 {
		t.Fatalf("unexpected takeover claim: %#v", secondClaim)
	}
	if err := service.AdvanceSequenceOwned(
		ctx,
		userID,
		first.Run.ID,
		1,
		firstClaim.Lease,
	); !errors.Is(err, conversation.ErrRunLeaseLost) {
		t.Fatalf("stale owner AdvanceSequenceOwned() error = %v", err)
	}

	event := agent.Event{
		ProtocolVersion: agent.ProtocolVersion,
		ExecutionID:     first.Run.ExecutionID,
		RunID:           first.Run.ID,
		Sequence:        1,
		Type:            "run.started",
		OccurredAt:      time.Now().UTC(),
		Data:            []byte(`{}`),
	}
	if inserted, err := service.RecordEventOwned(
		ctx,
		userID,
		first.Run.ID,
		event,
		secondClaim.Lease,
	); err != nil || !inserted {
		t.Fatalf("RecordEventOwned() inserted=%v error=%v", inserted, err)
	}
	if _, err := service.Finish(ctx, conversation.FinishGenerationParams{
		UserID:              userID,
		RunID:               first.Run.ID,
		AssistantMessageID:  first.Assistant.ID,
		Content:             "完成",
		Status:              string(agent.StatusCompleted),
		GenerationCompleted: time.Now().UTC(),
		Lease:               &secondClaim.Lease,
	}); err != nil {
		t.Fatalf("Finish() error = %v", err)
	}
	if _, ok, err := service.ClaimRun(
		ctx,
		first.Run.ID,
		"owner-c",
		time.Now().UTC().Add(time.Minute),
	); err != nil || ok {
		t.Fatalf("terminal ClaimRun() ok=%v error=%v", ok, err)
	}

	legacyConversation, err := service.Create(
		ctx,
		userID,
		conversation.DefaultAgent,
	)
	if err != nil {
		t.Fatalf("create legacy conversation: %v", err)
	}
	legacy, err := service.Start(ctx, conversation.StartGenerationParams{
		UserID:          userID,
		ConversationID:  legacyConversation.ID,
		ClientMessageID: auth.NewID(),
		RequestID:       auth.NewID(),
		Content:         "兼容入口继续由原 Handler 管理",
		AgentName:       conversation.DefaultAgent,
		ProtocolVersion: agent.ProtocolVersion,
	})
	if err != nil {
		t.Fatalf("create unmanaged run: %v", err)
	}
	if claimed, ok, err := service.ClaimNextRun(
		ctx,
		"owner-c",
		time.Now().UTC().Add(time.Minute),
	); err != nil || ok {
		t.Fatalf("unmanaged ClaimNextRun() claim=%#v ok=%v error=%v", claimed, ok, err)
	}
	if err := service.ReconcileStartup(ctx); err != nil {
		t.Fatalf("ReconcileStartup() error = %v", err)
	}
	legacyDetail, err := service.RunDetail(ctx, userID, legacy.Run.ID)
	if err != nil {
		t.Fatalf("legacy RunDetail() error = %v", err)
	}
	if legacyDetail.Run.Status != string(agent.StatusFailed) {
		t.Fatalf("unmanaged restart status = %q", legacyDetail.Run.Status)
	}
}
