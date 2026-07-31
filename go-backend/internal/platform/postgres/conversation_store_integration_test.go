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
		Data: json.RawMessage(`{
			"service_version":"integration-test",
			"agent_version":"agent-test",
			"graph_version":"graph-test",
			"prompt_bundle_hash":"bundle-test",
			"workflow_name":"chat_v1",
			"model_name":"model-test"
		}`),
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
	observabilityEvents := []agent.Event{
		{
			ProtocolVersion: agent.ProtocolVersion,
			ExecutionID:     generation.Run.ExecutionID,
			RunID:           generation.Run.ID,
			Sequence:        2,
			Type:            "prompt.used",
			OccurredAt:      time.Now().UTC(),
			Stage:           "generate",
			Data: json.RawMessage(`{
				"stage":"generate",
				"path":"agent/prompts/generate_default_system.txt",
				"sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
				"rendered_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
				"rendered_characters":128,
				"content_capture_level":"hashed"
			}`),
		},
		{
			ProtocolVersion: agent.ProtocolVersion,
			ExecutionID:     generation.Run.ExecutionID,
			RunID:           generation.Run.ID,
			Sequence:        3,
			Type:            "model.completed",
			OccurredAt:      time.Now().UTC(),
			SpanID:          "model-span-1",
			Category:        "model",
			Stage:           "generate",
			Data: json.RawMessage(`{
				"span_id":"model-span-1",
				"name":"model-test",
				"stage":"generate",
				"status":"completed",
				"duration_ms":32,
				"input_tokens":11,
				"output_tokens":7,
				"total_tokens":18
			}`),
		},
		{
			ProtocolVersion: agent.ProtocolVersion,
			ExecutionID:     generation.Run.ExecutionID,
			RunID:           generation.Run.ID,
			Sequence:        4,
			Type:            "tool.started",
			OccurredAt:      time.Now().UTC(),
			SpanID:          "tool-span-1",
			Category:        "tool",
			Stage:           "tool",
			Data: json.RawMessage(`{
				"span_id":"tool-span-1",
				"name":"get_current_date",
				"stage":"tool",
				"status":"started",
				"input":{"sha256":"safe"}
			}`),
		},
		{
			ProtocolVersion: agent.ProtocolVersion,
			ExecutionID:     generation.Run.ExecutionID,
			RunID:           generation.Run.ID,
			Sequence:        5,
			Type:            "tool.completed",
			OccurredAt:      time.Now().UTC(),
			SpanID:          "tool-span-1",
			Category:        "tool",
			Stage:           "tool",
			Data: json.RawMessage(`{
				"span_id":"tool-span-1",
				"name":"get_current_date",
				"stage":"tool",
				"status":"completed",
				"duration_ms":8,
				"output":{"sha256":"safe"}
			}`),
		},
		{
			ProtocolVersion: agent.ProtocolVersion,
			ExecutionID:     generation.Run.ExecutionID,
			RunID:           generation.Run.ID,
			Sequence:        6,
			Type:            "usage",
			OccurredAt:      time.Now().UTC(),
			Category:        "usage",
			Data: json.RawMessage(`{
				"model_name":"model-test",
				"input_tokens":11,
				"output_tokens":7,
				"total_tokens":18,
				"total_ms":45
			}`),
		},
		{
			ProtocolVersion: agent.ProtocolVersion,
			ExecutionID:     generation.Run.ExecutionID,
			RunID:           generation.Run.ID,
			Sequence:        7,
			Type:            "citation.created",
			OccurredAt:      time.Now().UTC(),
			Category:        "citation",
			Data: json.RawMessage(`{
				"citation_id":"source-1",
				"title":"Verified source",
				"url":"https://example.com/report",
				"snippet":"Public summary",
				"source_type":"web",
				"artifact_id":"research_evidence:abc",
				"sequence":1
			}`),
		},
	}
	for _, event := range observabilityEvents {
		inserted, err = service.RecordEvent(
			ctx,
			userID,
			generation.Run.ID,
			event,
		)
		if err != nil || !inserted {
			t.Fatalf(
				"observability RecordEvent(%s) inserted=%v error=%v",
				event.Type,
				inserted,
				err,
			)
		}
	}
	runs, err := service.ListRuns(ctx, userID, "", 10, nil)
	if err != nil {
		t.Fatalf("ListRuns() error = %v", err)
	}
	if len(runs) != 1 ||
		runs[0].TotalTokens != 18 ||
		runs[0].ModelCallCount != 1 ||
		runs[0].ToolCallCount != 1 ||
		runs[0].ActualRoute == nil ||
		*runs[0].ActualRoute != "chat_v1" ||
		runs[0].AgentVersion == nil ||
		*runs[0].AgentVersion != "agent-test" ||
		runs[0].GraphVersion == nil ||
		*runs[0].GraphVersion != "graph-test" ||
		runs[0].PromptBundleHash == nil ||
		*runs[0].PromptBundleHash != "bundle-test" {
		t.Fatalf("unexpected run summaries: %#v", runs)
	}
	detail, err := service.RunDetail(ctx, userID, generation.Run.ID)
	if err != nil {
		t.Fatalf("RunDetail() error = %v", err)
	}
	if len(detail.Spans) != 2 ||
		len(detail.Prompts) != 1 ||
		len(detail.Events) != 7 {
		t.Fatalf("unexpected run detail: %#v", detail)
	}
	if _, err := service.RunDetail(
		ctx,
		otherUserID,
		generation.Run.ID,
	); !errors.Is(err, conversation.ErrNotFound) {
		t.Fatalf("cross-user RunDetail() error = %v, want not found", err)
	}
	if err := service.MarkSequenceGap(
		ctx,
		userID,
		generation.Run.ID,
		7,
		9,
	); err != nil {
		t.Fatalf("MarkSequenceGap() error = %v", err)
	}
	if err := service.MarkSequenceReconciled(
		ctx,
		userID,
		generation.Run.ID,
		9,
	); err != nil {
		t.Fatalf("MarkSequenceReconciled() error = %v", err)
	}
	var (
		reconciliationRequired bool
		resolvedSequence       int64
	)
	if err := store.pool.QueryRow(ctx, `
		SELECT
			(metadata->'reconciliation'->>'required')::boolean,
			(metadata->'reconciliation'->>'resolved_sequence')::bigint
		FROM app_core.agent_runs
		WHERE id = $1
	`, generation.Run.ID).Scan(
		&reconciliationRequired,
		&resolvedSequence,
	); err != nil {
		t.Fatalf("query reconciliation metadata: %v", err)
	}
	if reconciliationRequired || resolvedSequence != 9 {
		t.Fatalf(
			"unexpected reconciliation state: required=%v sequence=%d",
			reconciliationRequired,
			resolvedSequence,
		)
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
	if _, err := service.Finish(ctx, conversation.FinishGenerationParams{
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
	var metadata struct {
		Citations []conversation.Citation `json:"citations"`
	}
	if err := json.Unmarshal(messages[1].Metadata, &metadata); err != nil {
		t.Fatalf("unmarshal assistant metadata: %v", err)
	}
	if len(metadata.Citations) != 1 ||
		metadata.Citations[0].CitationID != "source-1" ||
		metadata.Citations[0].ArtifactID != "research_evidence:abc" {
		t.Fatalf("assistant citations = %#v", metadata.Citations)
	}

	cancelledGeneration, err := service.Start(ctx, conversation.StartGenerationParams{
		UserID:          userID,
		ConversationID:  item.ID,
		ClientMessageID: auth.NewID(),
		RequestID:       auth.NewID(),
		Content:         "取消竞态测试",
		AgentName:       conversation.DefaultAgent,
		ProtocolVersion: agent.ProtocolVersion,
	})
	if err != nil {
		t.Fatalf("Start() cancellation race error = %v", err)
	}
	if err := service.RequestCancellation(
		ctx,
		userID,
		cancelledGeneration.Run.ID,
	); err != nil {
		t.Fatalf("RequestCancellation() error = %v", err)
	}
	if _, err := service.Finish(ctx, conversation.FinishGenerationParams{
		UserID:              userID,
		RunID:               cancelledGeneration.Run.ID,
		AssistantMessageID:  cancelledGeneration.Assistant.ID,
		Content:             "取消请求之后到达的完整回答",
		Status:              string(agent.StatusCompleted),
		GenerationCompleted: time.Now().UTC(),
	}); err != nil {
		t.Fatalf("Finish() cancellation race error = %v", err)
	}
	cancelledDetail, err := service.RunDetail(
		ctx,
		userID,
		cancelledGeneration.Run.ID,
	)
	if err != nil {
		t.Fatalf("RunDetail() cancellation race error = %v", err)
	}
	if cancelledDetail.Run.Status != string(agent.StatusCancelled) {
		t.Fatalf(
			"cancellation race status = %q, want %q",
			cancelledDetail.Run.Status,
			agent.StatusCancelled,
		)
	}
	messages, err = service.Messages(ctx, userID, item.ID, 50, nil)
	if err != nil {
		t.Fatalf("Messages() after cancellation race error = %v", err)
	}
	if got := messages[len(messages)-1].Status; got != "stopped" {
		t.Fatalf("cancelled assistant status = %q, want stopped", got)
	}

	afterCancellation, err := service.Start(ctx, conversation.StartGenerationParams{
		UserID:          userID,
		ConversationID:  item.ID,
		ClientMessageID: auth.NewID(),
		RequestID:       auth.NewID(),
		Content:         "取消后继续会话",
		AgentName:       conversation.DefaultAgent,
		ProtocolVersion: agent.ProtocolVersion,
	})
	if err != nil {
		t.Fatalf("Start() after cancellation error = %v", err)
	}
	if _, err := service.Finish(ctx, conversation.FinishGenerationParams{
		UserID:              userID,
		RunID:               afterCancellation.Run.ID,
		AssistantMessageID:  afterCancellation.Assistant.ID,
		Content:             "会话已解锁",
		Status:              string(agent.StatusCompleted),
		GenerationCompleted: time.Now().UTC(),
	}); err != nil {
		t.Fatalf("Finish() after cancellation error = %v", err)
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

func TestSkillResolutionIsPersistedOnceIntegration(t *testing.T) {
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
		DisplayName:  "skill-resolution-test",
		PasswordHash: "integration-test-hash",
	}); err != nil {
		t.Fatalf("CreateUser() error = %v", err)
	}
	t.Cleanup(func() {
		cleanupCtx, cleanupCancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cleanupCancel()
		_, _ = store.pool.Exec(cleanupCtx, "DELETE FROM app_core.users WHERE id=$1", userID)
	})

	service := conversation.NewService(store)
	item, err := service.Create(ctx, userID, conversation.DefaultAgent)
	if err != nil {
		t.Fatalf("Create() error = %v", err)
	}
	requestedSkill := "research"
	generation, err := service.Start(ctx, conversation.StartGenerationParams{
		UserID:          userID,
		ConversationID:  item.ID,
		ClientMessageID: auth.NewID(),
		RequestID:       auth.NewID(),
		Content:         "验证技能解析投影",
		AgentName:       conversation.DefaultAgent,
		ModelID:         "auto",
		RequestedSkill:  &requestedSkill,
		ProtocolVersion: agent.ProtocolVersion,
	})
	if err != nil {
		t.Fatalf("Start() error = %v", err)
	}

	resolutionData := json.RawMessage(`{
		"model_id":"auto",
		"requested_skill":"research",
		"resolved_skills":["research"],
		"primary_skill":"research",
		"selection_source":"user",
		"skill_snapshot":{"manifest_version":"1"},
		"model_snapshot":{"provider":"test","profile":"default_reasoning"},
		"context_package_id":null
	}`)
	resolutionEvent := agent.Event{
		ProtocolVersion: agent.ProtocolVersion,
		ExecutionID:     generation.Run.ExecutionID,
		RunID:           generation.Run.ID,
		Sequence:        1,
		Type:            "run.resolved",
		OccurredAt:      time.Now().UTC(),
		Data:            resolutionData,
	}
	inserted, err := service.RecordEvent(ctx, userID, generation.Run.ID, resolutionEvent)
	if err != nil || !inserted {
		t.Fatalf("first run.resolved inserted=%v error=%v", inserted, err)
	}
	inserted, err = service.RecordEvent(ctx, userID, generation.Run.ID, resolutionEvent)
	if err != nil || inserted {
		t.Fatalf("duplicate run.resolved inserted=%v error=%v", inserted, err)
	}

	equalResolution := resolutionEvent
	equalResolution.Sequence = 2
	inserted, err = service.RecordEvent(ctx, userID, generation.Run.ID, equalResolution)
	if err != nil || !inserted {
		t.Fatalf("equal run.resolved inserted=%v error=%v", inserted, err)
	}

	conflictingResolution := resolutionEvent
	conflictingResolution.Sequence = 3
	conflictingResolution.Data = json.RawMessage(`{
		"model_id":"auto",
		"requested_skill":"research",
		"resolved_skills":["research"],
		"primary_skill":"research",
		"selection_source":"compatibility",
		"skill_snapshot":{"manifest_version":"1"},
		"model_snapshot":{"provider":"test","profile":"default_reasoning"},
		"context_package_id":null
	}`)
	if inserted, err = service.RecordEvent(
		ctx,
		userID,
		generation.Run.ID,
		conflictingResolution,
	); !errors.Is(err, conversation.ErrSkillResolutionConflict) || inserted {
		t.Fatalf("conflicting run.resolved inserted=%v error=%v", inserted, err)
	}

	detail, err := service.RunDetail(ctx, userID, generation.Run.ID)
	if err != nil {
		t.Fatalf("RunDetail() error = %v", err)
	}
	if detail.Run.ModelID != "auto" ||
		detail.Run.RequestedSkill == nil || *detail.Run.RequestedSkill != requestedSkill ||
		string(detail.Run.ResolvedSkills) != `["research"]` ||
		detail.Run.PrimarySkill == nil || *detail.Run.PrimarySkill != requestedSkill ||
		detail.Run.SelectionSource == nil || *detail.Run.SelectionSource != "user" {
		t.Fatalf("unexpected persisted resolution: %#v", detail.Run)
	}
}
