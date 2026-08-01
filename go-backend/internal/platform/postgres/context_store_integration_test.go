package postgres

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"testing"
	"time"

	"github.com/starslittle/agent/go-backend/internal/agent"
	contextpackage "github.com/starslittle/agent/go-backend/internal/context"
	"github.com/starslittle/agent/go-backend/internal/conversation"
	"github.com/starslittle/agent/go-backend/internal/wiki"
)

func TestContextPackageFreezeIsolationAndRedactionIntegration(t *testing.T) {
	databaseURL := os.Getenv("TEST_DATABASE_URL")
	if databaseURL == "" {
		t.Skip("TEST_DATABASE_URL is not configured")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 45*time.Second)
	defer cancel()
	store, err := Open(ctx, databaseURL)
	if err != nil {
		t.Fatal(err)
	}
	defer store.Close()
	if err := store.Migrate(ctx); err != nil {
		t.Fatal(err)
	}
	userID := createPersonalSpaceTestUser(t, ctx, store, "context")
	otherUserID := createPersonalSpaceTestUser(t, ctx, store, "context-other")
	defer func() {
		cleanupCtx, cleanupCancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cleanupCancel()
		_, _ = store.pool.Exec(cleanupCtx, "DELETE FROM app_core.users WHERE id=ANY($1::uuid[])", []string{userID, otherUserID})
	}()
	wikiService := wiki.NewService(store)
	confirmed, err := wikiService.Create(ctx, wiki.CreateItemParams{UserID: userID, Type: wiki.TypeCurrentState, Domain: "career", Status: wiki.StatusConfirmed, Content: "正在寻找 AI 产品岗位", CreatedBy: wiki.ActorUser, Source: wiki.SourceInput{Type: wiki.SourceUserStated}})
	if err != nil {
		t.Fatal(err)
	}
	_, err = wikiService.Create(ctx, wiki.CreateItemParams{UserID: userID, Type: wiki.TypeCurrentState, Domain: "career", Status: wiki.StatusCandidate, Content: "未确认秘密", CreatedBy: wiki.ActorAgent, Source: wiki.SourceInput{Type: wiki.SourceAIInferred}})
	if err != nil {
		t.Fatal(err)
	}
	conversationService := conversation.NewService(store)
	conv, err := conversationService.Create(ctx, userID, conversation.DefaultAgent)
	if err != nil {
		t.Fatal(err)
	}
	generation, err := conversationService.CreateRun(ctx, conversation.StartGenerationParams{UserID: userID, ConversationID: conv.ID, ClientMessageID: "11111111-1111-4111-8111-111111111111", RequestID: "context-request", ExecutionID: "exec_context_test", Content: "结合我的情况给建议", AgentName: conversation.DefaultAgent, ModelID: "auto"})
	if err != nil {
		t.Fatal(err)
	}
	confidence := 0.9
	resolution := agent.SkillResolution{ModelID: "auto", ResolvedSkills: []string{}, SelectionSource: "direct", Confidence: &confidence, ReasonCode: "general_conversation", ModelSnapshot: json.RawMessage(`{"model_id":"auto"}`)}
	requirements := contextpackage.Requirements{ExecutionMode: "direct", Purpose: "conversation", NeedsPersonalContext: true, AllowedTypes: []string{wiki.TypeCurrentState}, AllowedDomains: []string{"career"}, ItemBudget: 3, CharacterBudget: 100}
	pkg, err := store.PrepareContextPackage(ctx, userID, generation.Run.ID, "22222222-2222-4222-8222-222222222222", resolution, requirements)
	if err != nil {
		t.Fatal(err)
	}
	if len(pkg.Items) != 1 || pkg.Items[0].ItemID != confirmed.Item.ID {
		t.Fatalf("package=%#v", pkg)
	}
	if _, err := store.FindContextPackageByRun(ctx, otherUserID, generation.Run.ID); !errors.Is(err, conversation.ErrNotFound) {
		t.Fatalf("cross user err=%v", err)
	}
	updated, err := wikiService.Update(ctx, wiki.UpdateItemParams{UserID: userID, ItemID: confirmed.Item.ID, ExpectedVersion: confirmed.Item.Version, Content: "已经入职", CreatedBy: wiki.ActorUser, Source: wiki.SourceInput{Type: wiki.SourceUserStated}})
	if err != nil {
		t.Fatal(err)
	}
	frozen, err := store.FindContextPackageByRun(ctx, userID, generation.Run.ID)
	if err != nil {
		t.Fatal(err)
	}
	if frozen.Items[0].Content != "正在寻找 AI 产品岗位" {
		t.Fatalf("historical content changed: %#v", frozen.Items)
	}
	if err := wikiService.DeletePermanently(ctx, userID, updated.Item.ID, updated.Item.Version); err != nil {
		t.Fatal(err)
	}
	redacted, err := store.FindContextPackageByRun(ctx, userID, generation.Run.ID)
	if err != nil {
		t.Fatal(err)
	}
	if len(redacted.Items) != 0 {
		t.Fatalf("permanently deleted content remained: %#v", redacted.Items)
	}
}
