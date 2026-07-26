package postgres

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"testing"
	"time"

	"github.com/starslittle/agent/go-backend/internal/agent"
	"github.com/starslittle/agent/go-backend/internal/auth"
	"github.com/starslittle/agent/go-backend/internal/conversation"
)

func TestConversationLifecycleIntegration(t *testing.T) {
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
	otherUserID := auth.NewID()
	for _, user := range []struct {
		id    string
		email string
	}{
		{userID, userID + "@example.com"},
		{otherUserID, otherUserID + "@example.com"},
	} {
		if _, err := store.CreateUser(ctx, auth.CreateUserParams{
			ID:           user.id,
			Email:        user.email,
			DisplayName:  "conversation-test",
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
				user.id,
			)
		})
	}

	service := conversation.NewService(store)
	item, err := service.Create(ctx, userID, conversation.DefaultAgent)
	if err != nil {
		t.Fatalf("Create() error = %v", err)
	}
	if item.Title != conversation.DefaultTitle {
		t.Fatalf("title = %q", item.Title)
	}
	if _, err := service.Get(ctx, otherUserID, item.ID); !errors.Is(err, conversation.ErrNotFound) {
		t.Fatalf("cross-user Get() error = %v, want not found", err)
	}

	generation, err := service.Start(ctx, conversation.StartGenerationParams{
		UserID:          userID,
		ConversationID:  item.ID,
		ClientMessageID: auth.NewID(),
		RequestID:       auth.NewID(),
		Content:         "这是第一条需要被持久化的消息",
		AgentName:       conversation.DefaultAgent,
		ProtocolVersion: agent.ProtocolVersion,
	})
	if err != nil {
		t.Fatalf("Start() error = %v", err)
	}
	if generation.Conversation.Title == conversation.DefaultTitle {
		t.Fatal("first message did not generate a conversation title")
	}
	startedEvent := agent.Event{
		ProtocolVersion: agent.ProtocolVersion,
		ExecutionID:     generation.Run.ExecutionID,
		RunID:           generation.Run.ID,
		Sequence:        1,
		Type:            "run.started",
		OccurredAt:      time.Now().UTC(),
		Data:            json.RawMessage(`{"service_version":"integration-test"}`),
	}
	inserted, err := service.RecordEvent(
		ctx,
		userID,
		generation.Run.ID,
		startedEvent,
	)
	if err != nil || !inserted {
		t.Fatalf("RecordEvent() inserted=%v error=%v", inserted, err)
	}
	inserted, err = service.RecordEvent(
		ctx,
		userID,
		generation.Run.ID,
		startedEvent,
	)
	if err != nil || inserted {
		t.Fatalf("duplicate RecordEvent() inserted=%v error=%v", inserted, err)
	}
	if _, err := service.Start(ctx, conversation.StartGenerationParams{
		UserID:          userID,
		ConversationID:  item.ID,
		ClientMessageID: *generation.UserMessage.ClientMessageID,
		RequestID:       auth.NewID(),
		Content:         "重复发送",
	}); !errors.Is(err, conversation.ErrDuplicateMessage) {
		t.Fatalf("duplicate Start() error = %v", err)
	}
	if _, err := service.Start(ctx, conversation.StartGenerationParams{
		UserID:          userID,
		ConversationID:  item.ID,
		ClientMessageID: auth.NewID(),
		RequestID:       auth.NewID(),
		Content:         "并发发送",
	}); !errors.Is(err, conversation.ErrGenerationActive) {
		t.Fatalf("concurrent Start() error = %v", err)
	}
	if err := service.Checkpoint(
		ctx,
		userID,
		generation.Assistant.ID,
		"部分回答",
	); err != nil {
		t.Fatalf("Checkpoint() error = %v", err)
	}
	if err := service.Finish(ctx, conversation.FinishGenerationParams{
		UserID:              userID,
		RunID:               generation.Run.ID,
		AssistantMessageID:  generation.Assistant.ID,
		Content:             "完整回答",
		Status:              "completed",
		GenerationCompleted: time.Now().UTC(),
	}); err != nil {
		t.Fatalf("Finish() error = %v", err)
	}

	messages, err := service.Messages(ctx, userID, item.ID, 50, nil)
	if err != nil {
		t.Fatalf("Messages() error = %v", err)
	}
	if len(messages) != 2 ||
		messages[0].Role != "user" ||
		messages[1].Role != "assistant" ||
		messages[1].Content != "完整回答" {
		t.Fatalf("unexpected messages: %#v", messages)
	}
	if _, err := service.Messages(ctx, otherUserID, item.ID, 50, nil); !errors.Is(err, conversation.ErrNotFound) {
		t.Fatalf("cross-user Messages() error = %v, want not found", err)
	}
	if _, err := service.Rename(ctx, userID, item.ID, "新的标题"); err != nil {
		t.Fatalf("Rename() error = %v", err)
	}
	if err := service.Delete(ctx, userID, item.ID); err != nil {
		t.Fatalf("Delete() error = %v", err)
	}
	if _, err := service.Get(ctx, userID, item.ID); !errors.Is(err, conversation.ErrNotFound) {
		t.Fatalf("Get() after delete error = %v, want not found", err)
	}
}
