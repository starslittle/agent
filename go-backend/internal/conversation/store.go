package conversation

import (
	"context"
	"errors"
	"time"

	"github.com/starslittle/agent/go-backend/internal/agent"
)

var (
	ErrNotFound            = errors.New("conversation not found")
	ErrInvalidInput        = errors.New("invalid conversation input")
	ErrGenerationActive    = errors.New("conversation already has an active generation")
	ErrDuplicateMessage    = errors.New("message already exists")
	ErrIdempotencyConflict = errors.New("idempotency key conflicts with an existing run")
	ErrRunLeaseLost        = errors.New("run supervisor lease lost")
)

type Store interface {
	CreateConversation(context.Context, string, string, string) (Conversation, error)
	ListConversations(context.Context, ListParams) ([]Conversation, error)
	FindConversation(context.Context, string, string) (Conversation, error)
	UpdateConversationTitle(context.Context, string, string, string) (Conversation, error)
	DeleteConversation(context.Context, string, string) error
	ListMessages(context.Context, MessageListParams) ([]Message, error)
	StartGeneration(context.Context, StartGenerationParams) (Generation, error)
	ClaimRun(context.Context, string, string, time.Time) (ClaimedRun, bool, error)
	ClaimNextRun(context.Context, string, time.Time) (ClaimedRun, bool, error)
	RenewRunLease(context.Context, string, RunLease, time.Time) error
	ReleaseRunLease(context.Context, string, RunLease) error
	LoadHistory(context.Context, string, string, int, int) ([]Message, error)
	CheckpointGeneration(context.Context, string, string, string) error
	CheckpointGenerationOwned(
		context.Context,
		string,
		string,
		string,
		string,
		int64,
		RunLease,
	) error
	AdvanceRunSequenceOwned(context.Context, string, string, int64, RunLease) error
	FinishGeneration(context.Context, FinishGenerationParams) (string, error)
	RecordAgentEvent(context.Context, string, string, agent.Event) (bool, error)
	RecordAgentEventOwned(
		context.Context,
		string,
		string,
		agent.Event,
		RunLease,
	) (bool, error)
	MarkSequenceGap(context.Context, string, string, int64, int64) error
	MarkSequenceReconciled(context.Context, string, string, int64) error
	RequestRunCancellation(context.Context, string, string) error
	ReconcileUnmanagedRuns(context.Context) error
	ListAgentRuns(context.Context, RunListParams) ([]RunSummary, error)
	FindAgentRunDetail(context.Context, string, string) (RunDetail, error)
}
