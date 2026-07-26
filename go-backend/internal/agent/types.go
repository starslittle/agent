package agent

import (
	"encoding/json"
	"errors"
	"fmt"
	"time"
)

const ProtocolVersion = 1

type Status string

const (
	StatusQueued          Status = "queued"
	StatusRunning         Status = "running"
	StatusCancelRequested Status = "cancel_requested"
	StatusCompleted       Status = "completed"
	StatusCancelled       Status = "cancelled"
	StatusFailed          Status = "failed"
	StatusTimedOut        Status = "timed_out"
)

var transitions = map[Status]map[Status]bool{
	StatusQueued: {
		StatusRunning: true, StatusCancelRequested: true,
		StatusFailed: true, StatusTimedOut: true,
	},
	StatusRunning: {
		StatusCancelRequested: true, StatusCompleted: true,
		StatusFailed: true, StatusTimedOut: true,
	},
	StatusCancelRequested: {
		StatusCancelled: true, StatusFailed: true, StatusTimedOut: true,
	},
	StatusCompleted: {},
	StatusCancelled: {},
	StatusFailed:    {},
	StatusTimedOut:  {},
}

func (s Status) Terminal() bool {
	return s == StatusCompleted || s == StatusCancelled ||
		s == StatusFailed || s == StatusTimedOut
}

func CanTransition(from, to Status) bool {
	return from == to || transitions[from][to]
}

type Message struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type RunRequest struct {
	ProtocolVersion int            `json:"protocol_version"`
	ExecutionID     string         `json:"execution_id"`
	RunID           string         `json:"run_id"`
	RequestID       string         `json:"request_id"`
	IdempotencyKey  string         `json:"idempotency_key"`
	ConversationID  string         `json:"conversation_id"`
	AgentName       string         `json:"agent_name"`
	Mode            string         `json:"mode,omitempty"`
	Query           string         `json:"query"`
	Messages        []Message      `json:"messages"`
	DeadlineMS      int64          `json:"deadline_ms"`
	Shadow          bool           `json:"shadow"`
	Metadata        map[string]any `json:"metadata,omitempty"`
	UserID          string         `json:"-"`
}

func (r RunRequest) Validate() error {
	if r.ProtocolVersion != ProtocolVersion {
		return fmt.Errorf("unsupported protocol version %d", r.ProtocolVersion)
	}
	for name, value := range map[string]string{
		"execution_id": r.ExecutionID,
		"run_id":       r.RunID,
		"request_id":   r.RequestID,
		"idempotency":  r.IdempotencyKey,
		"conversation": r.ConversationID,
		"query":        r.Query,
	} {
		if value == "" {
			return fmt.Errorf("%s is required", name)
		}
	}
	return nil
}

type Event struct {
	ProtocolVersion int             `json:"protocol_version"`
	ExecutionID     string          `json:"execution_id"`
	RunID           string          `json:"run_id"`
	Sequence        int64           `json:"sequence"`
	Type            string          `json:"type"`
	OccurredAt      time.Time       `json:"occurred_at"`
	Data            json.RawMessage `json:"data"`
}

func (e Event) Validate(expectedExecutionID string) error {
	if e.ProtocolVersion != ProtocolVersion {
		return fmt.Errorf("unsupported event protocol version %d", e.ProtocolVersion)
	}
	if e.ExecutionID == "" || e.ExecutionID != expectedExecutionID {
		return errors.New("event execution_id mismatch")
	}
	if e.RunID == "" || e.Sequence < 1 || e.Type == "" || e.OccurredAt.IsZero() {
		return errors.New("event is missing required fields")
	}
	if len(e.Data) == 0 {
		e.Data = json.RawMessage(`{}`)
	}
	return nil
}

func (e Event) SSEID() string {
	return fmt.Sprintf("%s:%d", e.ExecutionID, e.Sequence)
}

type Snapshot struct {
	ProtocolVersion int            `json:"protocol_version"`
	ServiceVersion  string         `json:"service_version"`
	ExecutionID     string         `json:"execution_id"`
	RunID           string         `json:"run_id"`
	Status          Status         `json:"status"`
	LastSequence    int64          `json:"last_sequence"`
	StartedAt       *time.Time     `json:"started_at,omitempty"`
	CompletedAt     *time.Time     `json:"completed_at,omitempty"`
	ExpiresAt       time.Time      `json:"expires_at"`
	Error           map[string]any `json:"error,omitempty"`
}
