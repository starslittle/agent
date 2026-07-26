package conversation

import (
	"context"
	"crypto/rand"
	"fmt"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/starslittle/agent/go-backend/internal/agent"
)

type Service struct {
	store Store
	now   func() time.Time
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
	if params.AgentName == "" {
		params.AgentName = DefaultAgent
	}
	if params.ClientMessageID == "" {
		params.ClientMessageID = newID()
	}
	if params.RequestID == "" {
		params.RequestID = newID()
	}
	if params.ExecutionID == "" {
		params.ExecutionID = "exec_" + strings.ReplaceAll(newID(), "-", "")
	}
	return s.store.StartGeneration(ctx, params)
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

func (s *Service) Finish(
	ctx context.Context,
	params FinishGenerationParams,
) error {
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

func (s *Service) MarkSequenceGap(
	ctx context.Context,
	userID string,
	runID string,
	expected int64,
	received int64,
) error {
	return s.store.MarkSequenceGap(ctx, userID, runID, expected, received)
}

func (s *Service) RequestCancellation(
	ctx context.Context,
	userID string,
	runID string,
) error {
	return s.store.RequestRunCancellation(ctx, userID, runID)
}

func (s *Service) Recover(ctx context.Context) error {
	return s.store.InterruptStaleGenerations(ctx)
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
