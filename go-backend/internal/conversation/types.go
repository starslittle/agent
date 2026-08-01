package conversation

import (
	"encoding/json"
	"net/url"
	"strings"
	"time"

	"github.com/starslittle/agent/go-backend/internal/agent"
	contextpackage "github.com/starslittle/agent/go-backend/internal/context"
)

const (
	DefaultTitle = "新的对话"
	DefaultAgent = "default_llm_agent"
)

type Conversation struct {
	ID                 string     `json:"id"`
	UserID             string     `json:"-"`
	Title              string     `json:"title"`
	AgentName          string     `json:"agent_name"`
	Status             string     `json:"status"`
	LastMessagePreview string     `json:"last_message_preview,omitempty"`
	LastMessageAt      *time.Time `json:"last_message_at,omitempty"`
	CreatedAt          time.Time  `json:"created_at"`
	UpdatedAt          time.Time  `json:"updated_at"`
}

type Message struct {
	ID              string          `json:"id"`
	ConversationID  string          `json:"conversation_id"`
	ClientMessageID *string         `json:"client_message_id,omitempty"`
	Role            string          `json:"role"`
	Content         string          `json:"content"`
	Status          string          `json:"status"`
	SequenceID      int64           `json:"sequence_id"`
	Metadata        json.RawMessage `json:"metadata,omitempty"`
	CreatedAt       time.Time       `json:"created_at"`
	UpdatedAt       time.Time       `json:"updated_at"`
	CompletedAt     *time.Time      `json:"completed_at,omitempty"`
}

type Citation struct {
	CitationID string `json:"citation_id"`
	Title      string `json:"title"`
	URL        string `json:"url"`
	Snippet    string `json:"snippet"`
	SourceType string `json:"source_type"`
	ArtifactID string `json:"artifact_id"`
	Sequence   int    `json:"sequence"`
}

type SkillConfirmation struct {
	SuggestedSkill string  `json:"suggested_skill"`
	Confidence     float64 `json:"confidence"`
	ReasonCode     string  `json:"reason_code"`
}

// ParseSkillConfirmation is the fail-closed boundary for confirmation data
// persisted in assistant message metadata. It intentionally excludes prompts
// and arbitrary event payloads.
func ParseSkillConfirmation(raw json.RawMessage) (SkillConfirmation, bool) {
	var confirmation SkillConfirmation
	if err := json.Unmarshal(raw, &confirmation); err != nil {
		return SkillConfirmation{}, false
	}
	confirmation.SuggestedSkill = strings.TrimSpace(confirmation.SuggestedSkill)
	confirmation.ReasonCode = strings.TrimSpace(confirmation.ReasonCode)
	if (confirmation.SuggestedSkill != "research" &&
		confirmation.SuggestedSkill != "fortune") ||
		confirmation.Confidence < 0 || confirmation.Confidence > 1 ||
		confirmation.ReasonCode != "automatic_confirmation_required" {
		return SkillConfirmation{}, false
	}
	return confirmation, true
}

// ParseCitation is the shared fail-closed boundary for durable message metadata
// and browser-visible citation events. Event data has already passed the
// agenttrace redaction boundary before this function is called.
func ParseCitation(raw json.RawMessage) (Citation, bool) {
	var citation Citation
	if err := json.Unmarshal(raw, &citation); err != nil {
		return Citation{}, false
	}
	citation.CitationID = strings.TrimSpace(citation.CitationID)
	citation.Title = truncateCitationField(citation.Title, 300)
	citation.URL = strings.TrimSpace(citation.URL)
	citation.Snippet = truncateCitationField(citation.Snippet, 500)
	citation.SourceType = strings.TrimSpace(citation.SourceType)
	citation.ArtifactID = strings.TrimSpace(citation.ArtifactID)
	if citation.CitationID == "" || len([]rune(citation.CitationID)) > 128 ||
		citation.Title == "" || citation.URL == "" ||
		len([]rune(citation.URL)) > 500 ||
		citation.ArtifactID == "" || len([]rune(citation.ArtifactID)) > 200 ||
		citation.Sequence < 1 || citation.Sequence > 10_000 {
		return Citation{}, false
	}
	switch citation.SourceType {
	case "web", "knowledge", "tool":
	default:
		return Citation{}, false
	}
	parsed, err := url.Parse(citation.URL)
	if err != nil || parsed.Hostname() == "" || parsed.User != nil ||
		(parsed.Scheme != "http" && parsed.Scheme != "https") {
		return Citation{}, false
	}
	return citation, true
}

func truncateCitationField(value string, limit int) string {
	runes := []rune(strings.TrimSpace(value))
	if len(runes) > limit {
		runes = runes[:limit]
	}
	return string(runes)
}

type Run struct {
	ID                 string
	ExecutionID        string
	IdempotencyKey     string
	ConversationID     string
	UserMessageID      string
	AssistantMessageID string
	RequestID          string
	AgentName          string
	ModelID            string
	RequestedSkill     *string
	ResolvedSkills     json.RawMessage
	PrimarySkill       *string
	SelectionSource    *string
	ContextPackageID   *string
	Metadata           json.RawMessage
	Status             string
	ProtocolVersion    int
	LastSequence       int64
}

type RunSummary struct {
	ID               string          `json:"id"`
	ExecutionID      string          `json:"execution_id"`
	TraceID          string          `json:"trace_id"`
	ConversationID   string          `json:"conversation_id"`
	AgentName        string          `json:"agent_name"`
	ModelID          string          `json:"model_id"`
	RequestedSkill   *string         `json:"requested_skill,omitempty"`
	ResolvedSkills   json.RawMessage `json:"resolved_skills"`
	PrimarySkill     *string         `json:"primary_skill,omitempty"`
	SelectionSource  *string         `json:"selection_source,omitempty"`
	ContextPackageID *string         `json:"context_package_id,omitempty"`
	ActualRoute      *string         `json:"actual_route,omitempty"`
	ModelName        *string         `json:"model_name,omitempty"`
	Status           string          `json:"status"`
	ProtocolVersion  int             `json:"protocol_version"`
	ServiceVersion   *string         `json:"service_version,omitempty"`
	AgentVersion     *string         `json:"agent_version,omitempty"`
	GraphVersion     *string         `json:"graph_version,omitempty"`
	PromptBundleHash *string         `json:"prompt_bundle_hash,omitempty"`
	InputTokens      int64           `json:"input_tokens"`
	OutputTokens     int64           `json:"output_tokens"`
	CachedTokens     int64           `json:"cached_tokens"`
	TotalTokens      int64           `json:"total_tokens"`
	ModelCallCount   int             `json:"model_call_count"`
	ToolCallCount    int             `json:"tool_call_count"`
	RetrievalCount   int             `json:"retrieval_count"`
	TotalDurationMS  *int64          `json:"total_duration_ms,omitempty"`
	ErrorCode        *string         `json:"error_code,omitempty"`
	ErrorDetail      *string         `json:"error_detail,omitempty"`
	FirstTokenAt     *time.Time      `json:"first_token_at,omitempty"`
	StartedAt        time.Time       `json:"started_at"`
	CompletedAt      *time.Time      `json:"completed_at,omitempty"`
	CreatedAt        time.Time       `json:"created_at"`
	OwnerUserID      string          `json:"user_id,omitempty"`
}

type RunEvent struct {
	Sequence            int64           `json:"sequence"`
	Type                string          `json:"type"`
	OccurredAt          time.Time       `json:"occurred_at"`
	TraceID             string          `json:"trace_id"`
	SpanID              *string         `json:"span_id,omitempty"`
	ParentSpanID        *string         `json:"parent_span_id,omitempty"`
	Category            *string         `json:"category,omitempty"`
	Stage               *string         `json:"stage,omitempty"`
	EventSchemaVersion  int             `json:"event_schema_version"`
	ContentCaptureLevel string          `json:"content_capture_level"`
	Data                json.RawMessage `json:"data"`
}

type RunSpan struct {
	SpanID       string          `json:"span_id"`
	ParentSpanID *string         `json:"parent_span_id,omitempty"`
	Type         string          `json:"type"`
	Name         string          `json:"name"`
	Stage        *string         `json:"stage,omitempty"`
	Status       string          `json:"status"`
	StartedAt    time.Time       `json:"started_at"`
	CompletedAt  *time.Time      `json:"completed_at,omitempty"`
	DurationMS   *int64          `json:"duration_ms,omitempty"`
	InputTokens  int64           `json:"input_tokens"`
	OutputTokens int64           `json:"output_tokens"`
	CachedTokens int64           `json:"cached_tokens"`
	TotalTokens  int64           `json:"total_tokens"`
	ErrorCode    *string         `json:"error_code,omitempty"`
	Attributes   json.RawMessage `json:"attributes"`
}

type RunPrompt struct {
	Sequence           int64   `json:"sequence"`
	Stage              string  `json:"stage"`
	Path               string  `json:"path"`
	PromptHash         string  `json:"prompt_hash"`
	RenderedHash       *string `json:"rendered_hash,omitempty"`
	RenderedCharacters *int    `json:"rendered_characters,omitempty"`
	Iteration          *int    `json:"iteration,omitempty"`
}

type RunDetail struct {
	Run          RunSummary            `json:"run"`
	Spans        []RunSpan             `json:"spans"`
	Events       []RunEvent            `json:"events"`
	Prompts      []RunPrompt           `json:"prompts"`
	ContextUsage *contextpackage.Usage `json:"context_usage,omitempty"`
}

type RunEventPage struct {
	ExecutionID     string
	ProtocolVersion int
	RunStatus       string
	AssistantStatus string
	LastSequence    int64
	ErrorCode       *string
	Events          []agent.Event
}

type RunListParams struct {
	UserID string
	Status string
	Limit  int
	Before *time.Time
}

type ObservabilityRunListParams struct {
	UserID    string
	Skill     string
	Workflow  string
	Model     string
	Status    string
	ErrorCode string
	From      *time.Time
	To        *time.Time
	Limit     int
	Before    *time.Time
}

type Generation struct {
	Conversation Conversation
	UserMessage  Message
	Assistant    Message
	Run          Run
	Replayed     bool
}

type ListParams struct {
	UserID string
	Limit  int
	Query  string
	Before *time.Time
}

type MessageListParams struct {
	UserID         string
	ConversationID string
	Limit          int
	BeforeSequence *int64
}

type StartGenerationParams struct {
	UserID            string
	ConversationID    string
	ClientMessageID   string
	RequestID         string
	ExecutionID       string
	IdempotencyKey    string
	Content           string
	AgentName         string
	ModelID           string
	RequestedSkill    *string
	ProtocolVersion   int
	Idempotent        bool
	SupervisorManaged bool
}

type RunLease struct {
	OwnerID   string
	Epoch     int64
	ExpiresAt time.Time
}

type ClaimedRun struct {
	Generation
	UserID         string
	PreviousStatus string
	Lease          RunLease
}

type FinishGenerationParams struct {
	UserID              string
	RunID               string
	AssistantMessageID  string
	Content             string
	Status              string
	ErrorCode           string
	ErrorDetail         string
	FirstTokenAt        *time.Time
	GenerationCompleted time.Time
	Lease               *RunLease
}

// ResolveTerminalStatus makes cancellation intent win over a late successful
// completion. This keeps the Product Run and assistant message consistent when
// DELETE races with Python's run.completed event.
func ResolveTerminalStatus(current string, requested string) string {
	currentStatus := agent.Status(current)
	if currentStatus.Terminal() {
		return current
	}
	if currentStatus == agent.StatusCancelRequested &&
		agent.Status(requested) == agent.StatusCompleted {
		return string(agent.StatusCancelled)
	}
	return requested
}
