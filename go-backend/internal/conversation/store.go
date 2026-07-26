package conversation

import (
	"context"
	"errors"

	"github.com/starslittle/agent/go-backend/internal/agent"
)

var (
	ErrNotFound         = errors.New("conversation not found")
	ErrInvalidInput     = errors.New("invalid conversation input")
	ErrGenerationActive = errors.New("conversation already has an active generation")
	ErrDuplicateMessage = errors.New("message already exists")
)

type Store interface {
	CreateConversation(context.Context, string, string, string) (Conversation, error)
	ListConversations(context.Context, ListParams) ([]Conversation, error)
	FindConversation(context.Context, string, string) (Conversation, error)
	UpdateConversationTitle(context.Context, string, string, string) (Conversation, error)
	DeleteConversation(context.Context, string, string) error
	ListMessages(context.Context, MessageListParams) ([]Message, error)
	StartGeneration(context.Context, StartGenerationParams) (Generation, error)
	LoadHistory(context.Context, string, string, int, int) ([]Message, error)
	CheckpointGeneration(context.Context, string, string, string) error
	FinishGeneration(context.Context, FinishGenerationParams) error
	RecordAgentEvent(context.Context, string, string, agent.Event) (bool, error)
	MarkSequenceGap(context.Context, string, string, int64, int64) error
	RequestRunCancellation(context.Context, string, string) error
	InterruptStaleGenerations(context.Context) error
	ListAgentRuns(context.Context, RunListParams) ([]RunSummary, error)
	FindAgentRunDetail(context.Context, string, string) (RunDetail, error)
}
