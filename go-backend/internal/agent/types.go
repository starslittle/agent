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
	ProtocolVersion    int             `json:"protocol_version"`
	ExecutionID        string          `json:"execution_id"`
	RunID              string          `json:"run_id"`
	Sequence           int64           `json:"sequence"`
	Type               string          `json:"type"`
	OccurredAt         time.Time       `json:"occurred_at"`
	TraceID            string          `json:"trace_id,omitempty"`
	SpanID             string          `json:"span_id,omitempty"`
	ParentSpanID       string          `json:"parent_span_id,omitempty"`
	Category           string          `json:"category,omitempty"`
	Stage              string          `json:"stage,omitempty"`
	EventSchemaVersion int             `json:"event_schema_version,omitempty"`
	ContentCapture     string          `json:"content_capture_level,omitempty"`
	Data               json.RawMessage `json:"data"`
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

// BrowserEventType are the canonical event types for the browser frontend protocol
// as defined in P0 stabilization plan. These map to internal RunStatus and
// are used for structured activity vs answer_delta separation.
type BrowserEventType string

const (
	BrowserEventMeta        BrowserEventType = "meta"
	BrowserEventActivity    BrowserEventType = "activity"
	BrowserEventAnswerDelta BrowserEventType = "answer_delta"
	BrowserEventArtifact    BrowserEventType = "artifact"
	BrowserEventDone        BrowserEventType = "done"
	BrowserEventError       BrowserEventType = "error"
)

// CreateRunResponse is the 202 Accepted response for Product Run creation
// (new contract for explicit Create Run + Attach separation). Includes
// client_message_id for idempotency contract.
type CreateRunResponse struct {
	ConversationID      string `json:"conversation_id"`
	UserMessageID       string `json:"user_message_id"`
	AssistantMessageID  string `json:"assistant_message_id"`
	RunID               string `json:"run_id"`
	ExecutionID         string `json:"execution_id"`
	ProtocolVersion     int    `json:"protocol_version"`
	Status              string `json:"status"`
	EventsURL           string `json:"events_url,omitempty"`
	ClientMessageID     string `json:"client_message_id"`
}

// AttachEventEnvelope holds starting_after and sequence for resume/attach
// per P0 rules. Sequence ensures no duplicate events on reconnect.
type AttachEventEnvelope struct {
	StartingAfter int64 `json:"starting_after,omitempty"`
	Sequence      int64 `json:"sequence,omitempty"`
}

// AssistantStatusMapping maps Python execution terminal status to
// assistant message status. Cancelled maps to "stopped" (no new truth source).
var AssistantStatusMapping = map[Status]string{
	StatusCancelled: "stopped",
	StatusCompleted: "completed",
	StatusFailed:    "failed",
	StatusTimedOut:  "failed",
}

// TerminalStatusToAssistantStatus returns the final assistant status
// for terminal runs. Used in contract tests only.
func TerminalStatusToAssistantStatus(s Status) string {
	if s == StatusCancelled {
		return "stopped"
	}
	return string(s)
}
