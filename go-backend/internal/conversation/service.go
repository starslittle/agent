package conversation

import (
	"context"
	"crypto/rand"
	"errors"
	"fmt"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/starslittle/agent/go-backend/internal/agent"
	contextpackage "github.com/starslittle/agent/go-backend/internal/context"
)

type Service struct {
	store Store
	now   func() time.Time
}

type contextStore interface {
	PrepareContextPackage(context.Context, string, string, string, agent.SkillResolution, contextpackage.Requirements) (contextpackage.Package, error)
	FindContextPackageByRun(context.Context, string, string) (contextpackage.Package, error)
}

func (s *Service) PrepareContextPackage(ctx context.Context, userID, runID, packageID string, resolution agent.SkillResolution, requirements contextpackage.Requirements) (contextpackage.Package, error) {
	store, ok := s.store.(contextStore)
	if !ok {
		return contextpackage.Package{}, errors.New("context package store unavailable")
	}
	return store.PrepareContextPackage(ctx, userID, runID, packageID, resolution, requirements)
}

func (s *Service) FindContextPackageByRun(ctx context.Context, userID, runID string) (contextpackage.Package, error) {
	store, ok := s.store.(contextStore)
	if !ok {
		return contextpackage.Package{}, errors.New("context package store unavailable")
	}
	return store.FindContextPackageByRun(ctx, userID, runID)
}

func NewService(store Store) *Service {
	return &Service{store: store, now: time.Now}
}

func (s *Service) Create(
	ctx context.Context,
	userID string,
	agentName string,
) (Conversation, error) {
	agentName = strings.TrimSpace(agentName)
	if agentName == "" {
		agentName = DefaultAgent
	}
	return s.store.CreateConversation(ctx, newID(), userID, agentName)
}

func (s *Service) List(
	ctx context.Context,
	userID string,
	limit int,
	query string,
	before *time.Time,
) ([]Conversation, error) {
	if limit <= 0 {
		limit = 30
	}
	if limit > 100 {
		limit = 100
	}
	return s.store.ListConversations(ctx, ListParams{
		UserID: userID,
		Limit:  limit,
		Query:  strings.TrimSpace(query),
		Before: before,
	})
}

func (s *Service) Get(ctx context.Context, userID, id string) (Conversation, error) {
	if strings.TrimSpace(id) == "" {
		return Conversation{}, ErrInvalidInput
	}
	return s.store.FindConversation(ctx, userID, id)
}

func (s *Service) Rename(
	ctx context.Context,
	userID string,
	id string,
	title string,
) (Conversation, error) {
	title = strings.Join(strings.Fields(title), " ")
	if title == "" || utf8.RuneCountInString(title) > 120 {
		return Conversation{}, ErrInvalidInput
	}
	return s.store.UpdateConversationTitle(ctx, userID, id, title)
}

func (s *Service) Delete(ctx context.Context, userID, id string) error {
	return s.store.DeleteConversation(ctx, userID, id)
}

func (s *Service) Messages(
	ctx context.Context,
	userID string,
	conversationID string,
	limit int,
	before *int64,
) ([]Message, error) {
	if limit <= 0 {
		limit = 50
	}
	if limit > 100 {
		limit = 100
	}
	return s.store.ListMessages(ctx, MessageListParams{
		UserID:         userID,
		ConversationID: conversationID,
		Limit:          limit,
		BeforeSequence: before,
	})
}

func (s *Service) Start(
	ctx context.Context,
	params StartGenerationParams,
) (Generation, error) {
	params.Content = strings.TrimSpace(params.Content)
	if params.Content == "" || utf8.RuneCountInString(params.Content) > 20000 {
		return Generation{}, ErrInvalidInput
	}
	selection, err := agent.NormalizeRunSelection(
		params.ModelID,
		params.RequestedSkill,
		params.AgentName,
	)
	if err != nil {
		return Generation{}, ErrInvalidInput
	}
	params.ModelID = selection.ModelID
	params.RequestedSkill = selection.RequestedSkill
	params.AgentName = selection.AgentName
	if params.ClientMessageID == "" {
		params.ClientMessageID = newID()
	}
	if params.RequestID == "" {
		params.RequestID = newID()
	}
	if params.ExecutionID == "" {
		params.ExecutionID = "exec_" + strings.ReplaceAll(newID(), "-", "")
	}
	if params.IdempotencyKey == "" {
		params.IdempotencyKey = params.ExecutionID
		if params.Idempotent {
			params.IdempotencyKey = params.ClientMessageID
		}
	}
	if utf8.RuneCountInString(params.IdempotencyKey) > 200 {
		return Generation{}, ErrInvalidInput
	}
	return s.store.StartGeneration(ctx, params)
}

func (s *Service) CreateRun(
	ctx context.Context,
	params StartGenerationParams,
) (Generation, error) {
	if strings.TrimSpace(params.ClientMessageID) == "" {
		return Generation{}, ErrInvalidInput
	}
	params.Idempotent = true
	params.SupervisorManaged = true
	params.ProtocolVersion = agent.ProtocolVersion
	return s.Start(ctx, params)
}

func (s *Service) ReconcileStartup(ctx context.Context) error {
	return s.store.ReconcileUnmanagedRuns(ctx)
}

func (s *Service) ClaimRun(
	ctx context.Context,
	runID string,
	ownerID string,
	leaseExpiresAt time.Time,
) (ClaimedRun, bool, error) {
	return s.store.ClaimRun(ctx, runID, ownerID, leaseExpiresAt)
}

func (s *Service) ClaimNextRun(
	ctx context.Context,
	ownerID string,
	leaseExpiresAt time.Time,
) (ClaimedRun, bool, error) {
	return s.store.ClaimNextRun(ctx, ownerID, leaseExpiresAt)
}

func (s *Service) RenewRunLease(
	ctx context.Context,
	runID string,
	lease RunLease,
	leaseExpiresAt time.Time,
) error {
	return s.store.RenewRunLease(ctx, runID, lease, leaseExpiresAt)
}

func (s *Service) ReleaseRunLease(
	ctx context.Context,
	runID string,
	lease RunLease,
) error {
	return s.store.ReleaseRunLease(ctx, runID, lease)
}

func (s *Service) History(
	ctx context.Context,
	userID string,
	conversationID string,
) ([]Message, error) {
	return s.store.LoadHistory(ctx, userID, conversationID, 40, 50000)
}

func (s *Service) Checkpoint(
	ctx context.Context,
	userID string,
	assistantMessageID string,
	content string,
) error {
	return s.store.CheckpointGeneration(ctx, userID, assistantMessageID, content)
}

func (s *Service) CheckpointOwned(
	ctx context.Context,
	userID string,
	runID string,
	assistantMessageID string,
	content string,
	sequence int64,
	lease RunLease,
) error {
	return s.store.CheckpointGenerationOwned(
		ctx,
		userID,
		runID,
		assistantMessageID,
		content,
		sequence,
		lease,
	)
}

func (s *Service) AdvanceSequenceOwned(
	ctx context.Context,
	userID string,
	runID string,
	sequence int64,
	lease RunLease,
) error {
	return s.store.AdvanceRunSequenceOwned(
		ctx,
		userID,
		runID,
		sequence,
		lease,
	)
}

func (s *Service) Finish(
	ctx context.Context,
	params FinishGenerationParams,
) (string, error) {
	if params.GenerationCompleted.IsZero() {
		params.GenerationCompleted = s.now().UTC()
	}
	return s.store.FinishGeneration(ctx, params)
}

func (s *Service) RecordEvent(
	ctx context.Context,
	userID string,
	runID string,
	event agent.Event,
) (bool, error) {
	return s.store.RecordAgentEvent(ctx, userID, runID, event)
}

func (s *Service) RecordEventOwned(
	ctx context.Context,
	userID string,
	runID string,
	event agent.Event,
	lease RunLease,
) (bool, error) {
	return s.store.RecordAgentEventOwned(ctx, userID, runID, event, lease)
}

func (s *Service) MarkSequenceGap(
	ctx context.Context,
	userID string,
	runID string,
	expected int64,
	received int64,
) error {
	return s.store.MarkSequenceGap(ctx, userID, runID, expected, received)
}

func (s *Service) MarkSequenceReconciled(
	ctx context.Context,
	userID string,
	runID string,
	resolvedSequence int64,
) error {
	return s.store.MarkSequenceReconciled(
		ctx,
		userID,
		runID,
		resolvedSequence,
	)
}

func (s *Service) RequestCancellation(
	ctx context.Context,
	userID string,
	runID string,
) error {
	return s.store.RequestRunCancellation(ctx, userID, runID)
}

func (s *Service) ListRuns(
	ctx context.Context,
	userID string,
	status string,
	limit int,
	before *time.Time,
) ([]RunSummary, error) {
	status = strings.TrimSpace(status)
	if status != "" {
		switch status {
		case "queued", "running", "cancel_requested", "completed",
			"cancelled", "failed", "timed_out":
		default:
			return nil, ErrInvalidInput
		}
	}
	if limit <= 0 {
		limit = 30
	}
	if limit > 100 {
		limit = 100
	}
	return s.store.ListAgentRuns(ctx, RunListParams{
		UserID: userID,
		Status: status,
		Limit:  limit,
		Before: before,
	})
}

func (s *Service) RunDetail(
	ctx context.Context,
	userID string,
	runID string,
) (RunDetail, error) {
	if strings.TrimSpace(runID) == "" {
		return RunDetail{}, ErrInvalidInput
	}
	return s.store.FindAgentRunDetail(ctx, userID, runID)
}

func (s *Service) RunEvents(
	ctx context.Context,
	userID string,
	runID string,
	startingAfter int64,
	limit int,
) (RunEventPage, error) {
	if strings.TrimSpace(userID) == "" || strings.TrimSpace(runID) == "" ||
		startingAfter < 0 {
		return RunEventPage{}, ErrInvalidInput
	}
	if limit <= 0 {
		limit = 256
	}
	if limit > 1000 {
		limit = 1000
	}
	return s.store.ListAgentRunEvents(ctx, userID, runID, startingAfter, limit)
}

func newID() string {
	value := make([]byte, 16)
	if _, err := rand.Read(value); err != nil {
		panic("crypto/rand unavailable")
	}
	value[6] = (value[6] & 0x0f) | 0x40
	value[8] = (value[8] & 0x3f) | 0x80
	return fmt.Sprintf(
		"%08x-%04x-%04x-%04x-%012x",
		value[0:4],
		value[4:6],
		value[6:8],
		value[8:10],
		value[10:16],
	)
}

func BuildTitle(content string) string {
	content = strings.Join(strings.Fields(content), " ")
	runes := []rune(content)
	if len(runes) > 32 {
		return string(runes[:32]) + "…"
	}
	if content == "" {
		return DefaultTitle
	}
	return content
}
